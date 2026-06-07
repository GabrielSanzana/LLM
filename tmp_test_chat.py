import requests

resp = requests.post('http://127.0.0.1:8000/api/chat', json={'message':'¿Cómo obtengo una partida de nacimiento?'})
print(resp.status_code)
print(resp.text)
