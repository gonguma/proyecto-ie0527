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

## Instalar dependencias

Para los paquete base de Python y GPIO:

```
sudo apt install -y python3 python3-venv python3-rpi.gpio \
                     python3-dev cmake build-essential
```

Crear carpeta para el proyecto:

```
mkdir -p ~/nodo_rf
cd ~/nodo_rf
```

Crear entorno virtual:

```
python3 -m venv .venv
source .venv/bin/activate
```

Por último, instalar la librería del nRF24:

```
pip install pyrf24
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

## 3. LEDs de estado

Usamos los GPIO como salidas a 3.3 V, con resistencia en serie.

### 3.1. Valores

- **Resistencia por LED:** 330 Ω (entre 220 Ω y 470 Ω está bien)

- **LED:**
    - Patita larga = ánodo (+)
    - Patita corta = cátodo (−)

### 3.2. LED1 verde (estado general)

- **Pi GPIO17 → pin físico 11**

**Conexión:**

1. GPIO17 → una fila de protoboard
2. Esa fila → resistencia 330 Ω → nueva fila
3. Nueva fila → ánodo (patita larga) del LED verde
4. Cátodo (patita corta) del LED verde → fila conectada a GND común

**Resultado:**

- GPIO17 en HIGH → LED1 verde encendido
- GPIO17 en LOW → LED1 verde apagado

### 3.3. LED2 amarillo (modo RX)

- **Pi GPIO27 → pin físico 13**

Conexión igual que LED1:

1. GPIO27 → resistencia 330 Ω → ánodo LED amarillo
2. Cátodo LED amarillo → GND

## 4. Botones TX y RX

**Esquema:** `GPIO ↔ botón ↔ GND`, usando pull-up interno en el código.

- Sin presionar → el pull-up interno mantiene el GPIO en 1 (HIGH)
- Al presionar → el botón lo conecta a GND → lectura 0 (LOW)

### 4.1. Botón TX

- **Pi GPIO23 → pin físico 16**

**Conexión:**

1. Una pata del botón → GPIO23
2. La otra pata del botón → GND

En software: GPIO23 como entrada con pull-up.

### 4.2. Botón RX

- **Pi GPIO24 → pin físico 18**

**Conexión:**

1. Una pata del botón → GPIO24
2. La otra pata del botón → GND

En software: GPIO24 como entrada con pull-up.

## 5. USB y pendrive

En la Pi Zero W:

- Power bank → conector micro-USB PWR IN
- Memoria USB → conector micro-USB “USB” usando un adaptador micro-USB OTG → USB-A hembra

El sistema operativo monta la USB en algo como:

```bash
/media/pi/<nombre_usb>/
```

**Tu código:**

- En el transmisor busca en esa ruta el `.txt` y lo envía.
- En el receptor escribe el archivo recibido (ej. `recibido.txt`) en la USB correspondiente.