# Proyecto - IE0527 - Ingeniería en Comunicaciones

Asumiendo:

Usuario: pi

Proyecto: /home/pi/nodo_rf

Entorno virtual: /home/pi/nodo_rf/.venv

Script: /home/pi/nodo_rf/nodo_rf.py

```
sudo nano /etc/systemd/system/nodo_rf.service
```

Agregar:

```
[Unit]
Description=Servicio Nodo RF (nRF24 + LEDs + botones)
After=network.target

[Service]
Type=simple
User=pi
Group=pi
WorkingDirectory=/home/pi/nodo_rf

# Ejecutar el Python dentro del virtualenv
ExecStart=/home/pi/nodo_rf/.venv/bin/python /home/pi/nodo_rf/nodo_rf.py

# Opcional: que reinicie si se cae
Restart=on-failure

# Opcional: para que los prints se vean al instante en journalctl
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
```

Para activar el servicio se usa lo siguiente:

```
sudo systemctl daemon-reload
sudo systemctl enable nodo_rf.service
sudo systemctl start nodo_rf.service
```
