def app(environ, start_response):
    """A bare-bones WSGI application for testing IIS integration."""
    status = '200 OK'
    headers = [('Content-Type', 'text/plain')]
    start_response(status, headers)
    return [b'Hello from IIS! Python is working.']
