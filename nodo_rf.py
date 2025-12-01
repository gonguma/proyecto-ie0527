#!/usr/bin/env python3
import os
import struct
import zlib
from pathlib import Path

import time
import sys
import RPi.GPIO as GPIO
from pyrf24 import RF24, RF24_PA_LOW, RF24_PA_MAX, RF24_250KBPS

# ----------------- Pines -----------------
# Numeración BCM
LED1 = 17       # LED verde (estado general)
LED2 = 27       # LED amarillo (modo RX)
BTN_TX = 23     # Botón TX
BTN_RX = 24     # Botón RX

# nRF24
CE_PIN = 22     # CE -> GPIO22
CSN_PIN = 0     # CSN = 0 -> /dev/spidev0.0 (CE0)

# Dirección RF (igual que en Arduino: "00001")
ADDRESS = b"00001"

# Crear objeto radio
radio = RF24(CE_PIN, CSN_PIN)

CHUNK_SIZE = 32  # tamaño de payload del nRF24
HEADER_PREFIX = b"HDR"

# ----------------- Inicialización GPIO -----------------
def setup_gpio():
    GPIO.setmode(GPIO.BCM)

    # LEDs como salida
    GPIO.setup(LED1, GPIO.OUT)
    GPIO.setup(LED2, GPIO.OUT)
    GPIO.output(LED1, GPIO.LOW)
    GPIO.output(LED2, GPIO.LOW)

    # Botones como entrada con pull-up interno
    # Botón conectado entre GPIO y GND
    GPIO.setup(BTN_TX, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(BTN_RX, GPIO.IN, pull_up_down=GPIO.PUD_UP)


# ----------------- Inicialización RF24 -----------------
def setup_radio():
    if not radio.begin():
        print("Error iniciando el radio RF24")
        sys.exit(1)

    radio.setPALevel(RF24_PA_MAX)
    radio.setChannel(108)
    radio.setDataRate(RF24_250KBPS)
    radio.setAutoAck(True)
    radio.setRetries(5, 15)

    # Abrimos un pipe de escritura y uno de lectura
    radio.openWritingPipe(ADDRESS)
    radio.openReadingPipe(1, ADDRESS)

    # Arrancamos en modo "standby TX listo"
    radio.stopListening()


# ----------------- Encontrar USB montada -----------------
"""def find_usb_mount():
    
    Devuelve la carpeta donde está montada la USB.
    Asume Raspberry Pi OS que monta en /media/<usuario>/<LABEL>.
    
    user = Path.home().name
    media_root = Path("/media") / user

    if not media_root.exists():
        raise RuntimeError(f"No se encontró la carpeta {media_root} (¿USB sin montar?)")

    mounts = [d for d in media_root.iterdir() if d.is_dir()]
    if not mounts:
        raise RuntimeError(f"No se encontró ninguna USB montada en {media_root}")

    # Como solo habrá una USB, tomamos la primera
    return mounts[0]"""


# ----------------- Encontrar Archivo txt -----------------
"""def find_source_txt_file():
    
    Busca el primer archivo .txt en la USB.
    Úsalo en el nodo transmisor.
    
    mount = find_usb_mount()
    txt_files = list(mount.glob("*.txt"))
    if not txt_files:
        raise RuntimeError(f"No se encontró ningún archivo .txt en {mount}")
    # Como la USB solo tendrá el archivo, tomamos el primero
    return txt_files[0]"""

# ----------------- Encontrar Archivo txt localmente -----------------
def find_source_txt_file():
    """
    Busca el primer archivo .txt en la carpeta donde está nodo_rf.py.
    Ignora 'recibido.txt' por si existiera.
    """
    base_dir = Path(__file__).resolve().parent
    txt_files = [
        p for p in base_dir.glob("*.txt")
        if p.name != "recibido.txt"
    ]
    if not txt_files:
        raise RuntimeError(f"No se encontró ningún archivo .txt en {base_dir}")
    # Tomamos el primero (como antes con la USB)
    return txt_files[0]



# ----------------- Ruta destino (RX) -----------------
"""def get_dest_usb_path(filename="recibido.txt"):
    
    Devuelve la ruta donde se guardará el archivo recibido en la USB.
    
    mount = find_usb_mount()
    return mount / filename"""


# ----------------- Utilidades -----------------
def wait_for_button_choice():
    """
    Espera a que se presione TX o RX.
    Devuelve "tx" o "rx".
    """
    print("Pulsa TX o RX para seleccionar modo...")
    while True:
        # Botones con pull-up -> reposo = 1, pulsado = 0
        if GPIO.input(BTN_TX) == GPIO.LOW:
            time.sleep(0.05)  # debounce
            if GPIO.input(BTN_TX) == GPIO.LOW:
                print("Botón TX detectado")
                # Esperar a que se suelte
                while GPIO.input(BTN_TX) == GPIO.LOW:
                    time.sleep(0.01)
                return "tx"

        if GPIO.input(BTN_RX) == GPIO.LOW:
            time.sleep(0.05)
            if GPIO.input(BTN_RX) == GPIO.LOW:
                print("Botón RX detectado")
                while GPIO.input(BTN_RX) == GPIO.LOW:
                    time.sleep(0.01)
                return "rx"

        time.sleep(0.01)

# ----------------- Error Blink -----------------
def blink_error(times=3, delay=0.2):
    """
    Parpadeo simple de LED1/LED2 para indicar error.
    """
    for _ in range(times):
        GPIO.output(LED1, GPIO.LOW)
        GPIO.output(LED2, GPIO.HIGH)
        time.sleep(delay)
        GPIO.output(LED1, GPIO.HIGH)
        GPIO.output(LED2, GPIO.LOW)
        time.sleep(delay)


# ----------------- Lógica de modo TX -----------------
def modo_tx():
    """
    Modo transmisor:
    - LED1 parpadea mientras envía el archivo .txt desde la USB.
    - Al terminar, LED1 queda encendido.
    """
    print("Entrando a modo TX...")
    GPIO.output(LED2, GPIO.LOW)  # aseguramos LED2 apagado

    try:
        source_path = find_source_txt_file()
    except Exception as e:
        print(f"[TX] ERROR buscando archivo en USB: {e}")
        blink_error()
        # Al final, dejar LED1 encendido (estado listo)
        GPIO.output(LED1, GPIO.HIGH)
        GPIO.output(LED2, GPIO.LOW)
        return

    ok = send_file_over_radio(source_path)
    if not ok:
        print("[TX] Transmisión fallida.")
        blink_error()
    else:
        print("[TX] Transmisión exitosa.")

    # En ambos casos regresamos a "idle": LED1 ON, LED2 OFF
    GPIO.output(LED1, GPIO.HIGH)
    GPIO.output(LED2, GPIO.LOW)


# ----------------- Modo RX en bucle -----------------
def modo_rx():
    """
    Bucle infinito en modo RX:
    - LED1 encendido indica "listo / idle".
    - Cuando se recibe un archivo, se guarda como recibido.txt en esta carpeta.
    - Tras cada intento (éxito o error), vuelve a estado idle.
    """
    base_dir = Path(__file__).resolve().parent
    dest_path = base_dir / "recibido.txt"

    while True:
        # Estado idle
        GPIO.output(LED1, GPIO.HIGH)
        GPIO.output(LED2, GPIO.LOW)
        print("\n[MAIN] Listo para recibir. LED1 encendido.")
        print("[MAIN] Esperando archivo...")

        ok = receive_file_over_radio(dest_path,
                                     header_timeout_s=60,
                                     data_timeout_s=2)

        if not ok:
            print("[MAIN] Intento de recepción fallido.")
            blink_error()
        else:
            print("[MAIN] Recepción OK. Archivo guardado.")

        # Pequeña pausa antes de esperar otra vez
        time.sleep(1)

    
# ----------------- Funcion para enviar archivo -----------------
def send_file_over_radio(path):
    """
    Envía el archivo indicado vía nRF24 en bloques de 32 bytes.
    Mientras envía, hace parpadear el LED1.
    Devuelve True si todo salió bien, False si hubo error.
    """
    # Leer archivo
    data = path.read_bytes()
    file_size = len(data)
    crc = zlib.crc32(data) & 0xFFFFFFFF

    print(f"[TX] Archivo: {path}")
    print(f"[TX] Tamaño: {file_size} bytes, CRC32: {crc:08X}")

    # Construir cabecera: "HDR" + file_size (4 bytes) + crc32 (4 bytes) + relleno
    header = HEADER_PREFIX + struct.pack("<II", file_size, crc)
    header = header.ljust(CHUNK_SIZE, b"\x00")

    # Aseguramos modo TX
    radio.stopListening()

    # Enviar cabecera (con algunos reintentos)
    print("[TX] Enviando cabecera...")
    ok = False
    for attempt in range(5):
        ok = radio.write(header)
        if ok:
            break
        print(f"[TX] Reintento cabecera {attempt+1}")
        time.sleep(0.05)

    if not ok:
        print("[TX] ERROR: no se pudo enviar la cabecera.")
        return False

    # Enviar datos en bloques de 32 bytes
    print("[TX] Enviando datos...")
    offset = 0
    led_state = False

    start_time = time.time()

    while offset < file_size:
        chunk = data[offset:offset + CHUNK_SIZE]
        if len(chunk) < CHUNK_SIZE:
            chunk = chunk.ljust(CHUNK_SIZE, b"\x00")

        # Parpadeo LED1 mientras se envía
        led_state = not led_state
        GPIO.output(LED1, GPIO.HIGH if led_state else GPIO.LOW)

        # Enviar chunk con algunos reintentos
        ok = False
        for attempt in range(3):
            ok = radio.write(chunk)
            if ok:
                break
            time.sleep(0.01)

        if not ok:
            print(f"[TX] ERROR: fallo al enviar chunk en offset {offset}.")
            return False

        offset += CHUNK_SIZE

    total_time = time.time() - start_time
    print(f"[TX] Archivo enviado completo en {total_time:.3f} s.")

    # Al terminar, LED1 queda encendido
    GPIO.output(LED1, GPIO.HIGH)
    GPIO.output(LED2, GPIO.LOW)
    return True

# ----------------- Funcion para recibir y guardar archivo -----------------
def receive_file_over_radio(dest_path, header_timeout_s=10, data_timeout_s=2):
    """
    Recibe un archivo vía nRF24 y lo guarda en dest_path.
    LED1 apagado, LED2 encendido mientras espera/recibe.
    Devuelve True si todo salió bien, False si hubo error.
    """
    print(f"[RX] Guardará archivo en: {dest_path}")

    # LEDs: LED1 OFF, LED2 ON
    GPIO.output(LED1, GPIO.LOW)
    GPIO.output(LED2, GPIO.HIGH)

    radio.startListening()

    # 1) Esperar cabecera
    print(f"[RX] Esperando cabecera (timeout {header_timeout_s} s)...")
    start = time.time()
    file_size = None
    crc_expected = None

    while True:
        if radio.available():
            packet = radio.read(CHUNK_SIZE)
            if not packet.startswith(HEADER_PREFIX):
                # Paquete inesperado, se ignora
                print("[RX] Paquete sin 'HDR' ignorado.")
                continue

            # Extraer tamaño y crc32
            try:
                file_size, crc_expected = struct.unpack("<II", packet[3:11])
            except struct.error:
                print("[RX] ERROR: cabecera mal formada.")
                radio.stopListening()
                return False

            print(f"[RX] Cabecera: tamaño={file_size} bytes, CRC32={crc_expected:08X}")
            break

        if time.time() - start > header_timeout_s:
            print("[RX] ERROR: timeout esperando cabecera.")
            radio.stopListening()
            return False

        time.sleep(0.01)

    # 2) Recibir datos
    print("[RX] Recibiendo datos...")
    received = bytearray()
    last_rx = time.time()

    while len(received) < file_size:
        if radio.available():
            chunk = radio.read(CHUNK_SIZE)
            received.extend(chunk)
            last_rx = time.time()
        else:
            if time.time() - last_rx > data_timeout_s:
                print("[RX] ERROR: timeout recibiendo datos.")
                radio.stopListening()
                return False
            time.sleep(0.005)

    radio.stopListening()

    # Recortar al tamaño exacto
    data = bytes(received[:file_size])

    # Verificar CRC
    crc_calc = zlib.crc32(data) & 0xFFFFFFFF
    if crc_calc != crc_expected:
        print(f"[RX] ERROR CRC: esperado {crc_expected:08X}, calculado {crc_calc:08X}")
        return False

    # Guardar archivo
    dest_path.write_bytes(data)
    print(f"[RX] Archivo recibido y guardado correctamente ({file_size} bytes).")

    # LEDs: LED2 OFF, LED1 ON
    GPIO.output(LED2, GPIO.LOW)
    GPIO.output(LED1, GPIO.HIGH)

    return True


# ----------------- Programa principal -----------------
def main():
    setup_gpio()
    setup_radio()

    # Estado inicial: LED1 encendido, LED2 apagado
    GPIO.output(LED1, GPIO.HIGH)
    GPIO.output(LED2, GPIO.LOW)
    print("Estado inicial: LED1 encendido (start-up).")

    while True:
        # Esperamos que el usuario escoja TX o RX
        choice = wait_for_button_choice()

        if choice == "tx":
            modo_tx()
        elif choice == "rx":
            modo_rx(timeout_s=10)
        # Después de cada modo volvemos al "idle":
        # LED1 ON, LED2 OFF y esperamos de nuevo TX/RX.


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nSaliendo por Ctrl+C...")
    finally:
        GPIO.cleanup()
