from django.shortcuts import render
from django.http import HttpResponse
from django.core.files.storage import FileSystemStorage

def upload_file(request):
    if request.method == 'POST' and request.FILES['myfile']:
        myfile = request.FILES['myfile']
        fs = FileSystemStorage()
        filename = fs.save(myfile.name, myfile)
        uploaded_file_url = fs.url(filename)
        return render(request, 'trading_app/upload.html', {
            'uploaded_file_url': uploaded_file_url
        })
    return render(request, 'trading_app/upload.html')
