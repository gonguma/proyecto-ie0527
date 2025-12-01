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

## Conexión del Hardware

Cada nodo tiene:

* 1× Raspberry Pi Zero W
* 1× nRF24L01+ PA+LNA (módulo con antena)
* 1× Regulador 5 V → 3.3 V solo para el nRF
* 2× LEDs:

    * LED1 verde (estado general)
    * LED2 amarillo (modo RX)

* 2× botones:

    * Botón TX (modo transmisor)
    * Botón RX (modo receptor)

* 1× Power bank 5 V
* 1× USB OTG (para la memoria USB)

Todo comparte la misma tierra (GND).

## Alimentación

### 1.1. Power bank → Raspberry Pi

* Power bank 5 V → conector micro-USB PWR IN de la Pi Zero W.
(El otro micro-USB “USB” queda libre para el OTG).

La Pi se enciende sola al conectar la batería.

### 1.2. Pi → Regulador 5 V → 3.3 V

En el header de 40 pines de la Pi:

* 5 V → pin físico 2 o 4
* GND → por ejemplo pin físico 6

Conexiones:

* Pin 5 V de la Pi (2/4) → pin IN del regulador 3.3 V
* Pin GND de la Pi (6) → pin GND del regulador

Condensadores en el regulador (recomendado):

* Entre IN y GND: 10–22 µF (electrolítico)
* Entre OUT y GND: 22–47 µF + 100 nF (electrolítico + cerámico)

### 1.3. Regulador → nRF24L01+ PA+LNA

En el regulador:

* Pin OUT (3.3 V) → pin VCC del nRF
* Pin GND → pin GND del nRF

Condensador cerca del nRF:

* Entre VCC y GND del nRF: 47–100 µF + 100 nF

Importante:
GND de Pi, regulador, nRF, LEDs y botones es el mismo nodo (todo unido).

## Conexión del nRF24L01+ PA+LNA a la Pi (SPI + control)

### 2.1. Pines de la Raspberry Pi (numeración BCM → pin físico)

* SCK / SCLK → GPIO11 → pin físico 23
* MOSI → GPIO10 → pin físico 19
* MISO → GPIO9 → pin físico 21
* CSN / CE0 (SPI0) → GPIO8 → pin físico 24
* CE del nRF → GPIO22 → pin físico 15
* GND → pin físico 6 (ya usado como común)

### 2.2. Pines típicos del nRF24L01+ PA+LNA

1. GND
2. VCC (3.3 V)
3. CE
4. CSN
5. SCK
6. MOSI
7. MISO
8. IRQ
