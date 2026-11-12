import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from market.models import PortfolioTrade, Symbol
from market.services.explore import (
    ask_market_bot,
    clamp_date,
    company_choices,
    coverage,
    default_purchase,
    load_equity_frame,
    market_board,
    market_context,
    nairobi_today,
    parse_date,
    portfolio_page,
    simulate_page,
    split_amount,
    stock_page,
)
from market.services.portfolio import combine_trades


def _frame_or_none():
    try:
        return load_equity_frame()
    except Exception as exc:
        return exc


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    error = ""
    if request.method == "POST":
        user = authenticate(
            request,
            username=request.POST.get("username", "").strip(),
            password=request.POST.get("password", ""),
        )
        if user is None or not user.is_active:
            error = "That username or password is not valid."
        else:
            login(request, user)
            next_url = request.GET.get("next") or ""
            if not next_url.startswith("/") or next_url.startswith("//"):
                next_url = ""
            return redirect(next_url or "dashboard")
    return render(request, "market/login.html", {"error": error})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("login")


def _symbols(frame):
    return [item["code"] for item in company_choices(frame)]


def _stock_state(request, frame):
    earliest, latest = coverage(frame)
    symbols = _symbols(frame)
    symbol = request.GET.get("code") or "DTK"
    if symbol not in symbols:
        symbol = symbols[0]
    start = clamp_date(parse_date(request.GET.get("start"), earliest), earliest, latest)
    end = clamp_date(parse_date(request.GET.get("end"), latest), earliest, latest)
    if start > end:
        start, end = earliest, latest
    style = request.GET.get("style") if request.GET.get("style") in {"line", "candle"} else "line"
    try:
        amount = float(request.GET.get("amount") or 1_000_000)
    except ValueError:
        amount = 1_000_000
    amount = max(amount, 100)
    buy = clamp_date(parse_date(request.GET.get("buy"), default_purchase(earliest, latest)), earliest, latest)
    sell = clamp_date(parse_date(request.GET.get("sell"), latest), earliest, latest)
    page = stock_page(frame, symbol, start, end, style, amount, buy, sell)
    page.update({
        "symbol": symbol,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "style": style,
        "amount": f"{amount:.2f}",
        "buy": buy.isoformat(),
        "sell": sell.isoformat(),
    })
    return page


def _roll_forward(posted, previous, pinned, latest):
    """Keep a date the user chose. A date this page filled in earlier follows the newest close."""
    if pinned:
        return posted
    if previous and posted.isoformat() == previous:
        return latest
    return posted


def _sim_state(request, frame):
    earliest, latest = coverage(frame)
    symbols = _symbols(frame)
    raw = request.session.get("sim") or {}
    defaults = [code for code in ["DTK", "SCOM", "EQTY", "KCB"] if code in symbols][:4] or symbols[:3]
    codes = [code for code in raw.get("codes", defaults) if code in symbols][:8]
    if not codes:
        codes = defaults
    try:
        pot = float(raw.get("pot", 100_000))
    except (TypeError, ValueError):
        pot = 100_000
    pot = max(pot, 100)
    alloc = {code: float((raw.get("alloc") or {}).get(code, 0)) for code in codes}
    stored_codes = list((raw.get("alloc") or {}).keys())
    if not raw.get("alloc") or stored_codes != codes:
        alloc = split_amount(pot, codes)
    buy = clamp_date(parse_date(raw.get("buy"), default_purchase(earliest, latest)), earliest, latest)
    sell = latest if not raw.get("sell_pinned") else clamp_date(parse_date(raw.get("sell"), latest), earliest, latest)
    chart_start = clamp_date(parse_date(raw.get("chart_start"), earliest), earliest, latest)
    chart_end = latest if not raw.get("chart_end_pinned") else clamp_date(parse_date(raw.get("chart_end"), latest), earliest, latest)
    if chart_start > chart_end:
        chart_start, chart_end = earliest, latest
    state = {
        "pot": pot,
        "codes": codes,
        "alloc": alloc,
        "buy": buy.isoformat(),
        "sell": sell.isoformat(),
        "sell_pinned": bool(raw.get("sell_pinned")) and sell < latest,
        "chart_start": chart_start.isoformat(),
        "chart_end": chart_end.isoformat(),
        "chart_end_pinned": bool(raw.get("chart_end_pinned")) and chart_end < latest,
    }
    if request.session.get("sim") != state:
        request.session["sim"] = state
    page = simulate_page(frame, pot, codes, alloc, buy, sell, chart_start, chart_end)
    page["form"] = {
        "pot": f"{pot:.2f}",
        "codes": codes,
        "alloc": [{"code": code, "amount": f"{alloc[code]:.2f}"} for code in codes],
        "buy": state["buy"],
        "sell": state["sell"],
        "chart_start": state["chart_start"],
        "chart_end": state["chart_end"],
    }
    return page


def _save_sim(request, frame):
    earliest, latest = coverage(frame)
    symbols = _symbols(frame)
    try:
        pot = max(float(request.POST.get("pot") or 0), 100)
    except ValueError:
        pot = 100_000
    posted = [code for code in request.POST.getlist("codes") if code in symbols]
    if len(posted) > 8:
        messages.warning(request, "Only the first 8 stocks are used.")
    codes = posted[:8]
    buy = clamp_date(parse_date(request.POST.get("buy"), default_purchase(earliest, latest)), earliest, latest)
    previous = request.session.get("sim") or {}
    sell = _roll_forward(
        clamp_date(parse_date(request.POST.get("sell"), latest), earliest, latest),
        previous.get("sell"),
        bool(previous.get("sell_pinned")),
        latest,
    )
    chart_start = clamp_date(parse_date(request.POST.get("chart_start"), earliest), earliest, latest)
    chart_end = _roll_forward(
        clamp_date(parse_date(request.POST.get("chart_end"), latest), earliest, latest),
        previous.get("chart_end"),
        bool(previous.get("chart_end_pinned")),
        latest,
    )
    previous_key = (round(float(previous.get("pot", 0)), 2), tuple(previous.get("codes") or []))
    current_key = (round(pot, 2), tuple(codes))
    if current_key != previous_key or not codes:
        alloc = split_amount(pot, codes)
    else:
        alloc = {}
        for code in codes:
            try:
                alloc[code] = max(float(request.POST.get(f"alloc_{code}") or 0), 0)
            except ValueError:
                alloc[code] = 0
        if request.POST.get("action") == "move" and len(codes) > 1:
            source = request.POST.get("move_from")
            destination = request.POST.get("move_to")
            try:
                moved = float(request.POST.get("move_amount") or 0)
            except ValueError:
                moved = 0
            if source in alloc and destination in alloc:
                if source == destination:
                    messages.warning(request, "Choose a different stock to add the cash to.")
                elif moved <= 0:
                    messages.warning(request, "Enter an amount to move.")
                elif moved > alloc[source] + 0.001:
                    messages.error(request, f"{source} only has KSh {alloc[source]:,.2f}.")
                else:
                    alloc[source] = round(alloc[source] - moved, 2)
                    alloc[destination] = round(alloc[destination] + moved, 2)
    request.session["sim"] = {
        "pot": pot,
        "codes": codes,
        "alloc": alloc,
        "buy": buy.isoformat(),
        "sell": sell.isoformat(),
        "sell_pinned": sell < latest,
        "chart_start": chart_start.isoformat(),
        "chart_end": chart_end.isoformat(),
        "chart_end_pinned": chart_end < latest,
    }
    request.session.modified = True


def _trade_rows(user, extra=None):
    rows = []
    for trade in user.portfolio_trades.select_related("symbol"):
        rows.append({
            "id": trade.id,
            "code": trade.symbol.code,
            "side": trade.side,
            "shares": trade.shares,
            "price": trade.price,
            "trade_date": trade.trade_date,
        })
    if extra:
        rows.append(extra)
    return rows


def _save_trade(request, frame):
    earliest, latest = coverage(frame)
    code = request.POST.get("trade_code", "")
    side = request.POST.get("side", "buy").lower()
    if side not in {"buy", "sell"}:
        side = "buy"
    try:
        shares = int(request.POST.get("shares") or 0)
        price = Decimal(request.POST.get("price") or "0")
    except (InvalidOperation, ValueError):
        messages.error(request, "Enter a whole number of shares and a price.")
        return
    if shares < 1 or price <= 0:
        messages.error(request, "Shares and price must be above zero.")
        return
    entry_max = max(latest, nairobi_today())
    trade_date = clamp_date(parse_date(request.POST.get("trade_date"), nairobi_today()), earliest, entry_max)
    symbol = Symbol.objects.filter(code=code).first()
    if symbol is None:
        messages.error(request, f"{code} is not in the price database yet.")
        return
    draft = _trade_rows(request.user, {
        "id": None,
        "code": code,
        "side": side,
        "shares": shares,
        "price": price,
        "trade_date": trade_date,
    })
    _positions, error = combine_trades(draft)
    if error:
        messages.error(request, error)
        return
    PortfolioTrade.objects.create(
        user=request.user,
        symbol=symbol,
        side=side,
        shares=shares,
        price=price,
        trade_date=trade_date,
    )


def _remove_trade(request):
    try:
        trade_id = int(request.POST.get("trade_id") or 0)
    except ValueError:
        return
    saved = _trade_rows(request.user)
    remaining = [trade for trade in saved if trade["id"] != trade_id]
    if len(remaining) == len(saved):
        return
    _positions, error = combine_trades(remaining)
    if error:
        messages.error(request, error)
        return
    PortfolioTrade.objects.filter(pk=trade_id, user=request.user).delete()


@login_required
def dashboard(request):
    section = request.GET.get("section", "market")
    if section not in {"stock", "simulate", "portfolio", "market"}:
        section = "market"
    loaded = _frame_or_none()
    if isinstance(loaded, Exception):
        return render(request, "market/dashboard.html", {
            "section": section,
            "load_error": str(loaded),
            "chat_messages": request.session.get("chat_messages", []),
        })
    frame = loaded
    if request.method == "POST" and section == "simulate":
        _save_sim(request, frame)
        return redirect("/?section=simulate")
    if request.method == "POST" and section == "portfolio":
        if request.POST.get("action") == "remove":
            _remove_trade(request)
        else:
            _save_trade(request, frame)
        return redirect("/?section=portfolio")
    earliest, latest = coverage(frame)
    context = {
        "section": section,
        "companies": company_choices(frame),
        "record_from": f"{earliest:%d %b %Y}",
        "record_to": f"{latest:%d %b %Y}",
        "chat_messages": request.session.get("chat_messages", []),
        "focus_code": request.GET.get("code") if section == "stock" else "",
    }
    if section == "stock":
        context["stock"] = _stock_state(request, frame)
        context["focus_code"] = context["stock"].get("symbol", "")
    elif section == "simulate":
        context["sim"] = _sim_state(request, frame)
    elif section == "portfolio":
        context["portfolio"] = portfolio_page(request.user, frame)
    else:
        direction = request.GET.get("direction") or "all"
        sector = request.GET.get("sector") or ""
        trend = request.GET.get("trend") or "3m"
        context["board"] = market_board(frame, direction, sector, trend)
    return render(request, "market/dashboard.html", context)


@login_required
@require_POST
def chat_view(request):
    try:
        payload = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        payload = request.POST
    question = str(payload.get("message") or "").strip()
    if payload.get("clear"):
        request.session["chat_messages"] = []
        request.session.modified = True
        return JsonResponse({"cleared": True})
    if not question:
        return JsonResponse({"error": "Enter a question."}, status=400)
    loaded = _frame_or_none()
    if isinstance(loaded, Exception):
        return JsonResponse({"error": str(loaded)}, status=503)
    history = list(request.session.get("chat_messages", []))
    history.append({"role": "user", "content": question})
    try:
        answer = ask_market_bot(
            history,
            market_context(loaded, question, str(payload.get("focus") or "")),
        )
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=502)
    history.append({"role": "assistant", "content": answer})
    request.session["chat_messages"] = history[-12:]
    request.session.modified = True
    return JsonResponse({"answer": answer})
