# Upload a file to the iReader WiFi-transfer server (test.php?action=addBook).
import mimetypes
import os
import sys
import urllib.request
import uuid

HOST = os.environ.get("IREADER_HOST", "http://<ireader-ip>:10123")


def post_file(path):
    name = os.path.basename(path)
    boundary = "----upload" + uuid.uuid4().hex
    ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
    with open(path, "rb") as f:
        data = f.read()

    body = b""
    body += ("--%s\r\n" % boundary).encode()
    body += ('Content-Disposition: form-data; name="file"; filename="%s"\r\n' % name).encode("utf-8")
    body += ("Content-Type: %s\r\n\r\n" % ctype).encode()
    body += data
    body += ("\r\n--%s--\r\n" % boundary).encode()

    req = urllib.request.Request(HOST + "/test.php?action=addBook", data=body,
                                 headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read().decode("utf-8", "replace")[:400]


def list_books():
    req = urllib.request.Request(HOST + "/test.php?action=getBooksList&t=1")
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")[:1200]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: upload_ireader.py <file>")
        sys.exit(2)
    print("upload:", post_file(sys.argv[1]))
    print("list:", list_books())
