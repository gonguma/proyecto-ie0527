#!/usr/bin/env python3
import struct
import zlib
from pathlib import Path
import time
import sys

import RPi.GPIO as GPIO
from pyrf24 import RF24, RF24_PA_MAX, RF24_250KBPS, RF24_DRIVER

# ----------------- Pines (BCM) -----------------
LED1 = 17       # LED verde (estado general / idle)
LED2 = 27       # LED amarillo (modo RX)

BTN_TX = 23     # Botón TX (entre GPIO23 y GND)
BTN_RX = 24     # Botón RX (entre GPIO24 y GND)

# nRF24
CE_PIN = 22     # CE -> GPIO22 (pin físico 15)
CSN_PIN = 0     # CSN = 0 -> /dev/spidev0.0 (CE0)

# Dirección RF (igual que en Arduino: "00001")
ADDRESS = b"00001"

# Objeto radio global
radio = RF24(CE_PIN, CSN_PIN)

CHUNK_SIZE = 32          # tamaño de payload del nRF24
HEADER_PREFIX = b"HDR"   # prefijo de cabecera


# ----------------- GPIO -----------------
def setup_gpio():
    GPIO.setmode(GPIO.BCM)

    # LEDs
    GPIO.setup(LED1, GPIO.OUT)
    GPIO.setup(LED2, GPIO.OUT)
    GPIO.output(LED1, GPIO.LOW)
    GPIO.output(LED2, GPIO.LOW)

    # Botones con pull-up interno (reposo = 1, presionado = 0)
    GPIO.setup(BTN_TX, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(BTN_RX, GPIO.IN, pull_up_down=GPIO.PUD_UP)


# ----------------- RF24 -----------------
def setup_radio():
    print("RF24_DRIVER =", RF24_DRIVER)
    print(f"Inicializando radio en CE={CE_PIN}, CSN={CSN_PIN} (/dev/spidev0.0)")

    if not radio.begin():
        print("Error iniciando el radio RF24 (radio.begin() devolvió False).")
        print("Revisa: SPI habilitado, CE/CSN/SCK/MOSI/MISO, VCC=3.3V y GND común.")
        sys.exit(1)

    radio.setPALevel(RF24_PA_MAX)
    radio.setChannel(108)
    radio.setDataRate(RF24_250KBPS)
    radio.setAutoAck(True)
    radio.setRetries(5, 15)

    # Configuramos pipes para TX y RX (mismo address)
    radio.openWritingPipe(ADDRESS)
    radio.openReadingPipe(1, ADDRESS)

    # Arrancamos en "standby" (no escuchando) y LEDs en idle
    radio.stopListening()
    print("Radio inicializado correctamente.")
    try:
        print("radio.is_chip_connected =", radio.is_chip_connected)
    except Exception:
        pass


# ----------------- Utilidades -----------------
def blink_error(times=3, delay=0.2):
    """Parpadeo simple LED1/LED2 para indicar error."""
    for _ in range(times):
        GPIO.output(LED1, GPIO.LOW)
        GPIO.output(LED2, GPIO.HIGH)
        time.sleep(delay)
        GPIO.output(LED1, GPIO.HIGH)
        GPIO.output(LED2, GPIO.LOW)
        time.sleep(delay)

# ----------------- File helpers -----------------
"""def find_source_txt_file():
    
    Busca el primer archivo .txt en la carpeta tests,
    que debe estar en el mismo directorio que este script.
    Ej: /home/pi/nodo_rf/tests/tester1.txt
    
    base_dir = Path(__file__).resolve().parent
    tests_dir = base_dir / "tests"

    if not tests_dir.exists():
        raise RuntimeError(f"No existe la carpeta {tests_dir}")

    txt_files = [
        p for p in tests_dir.glob("*.txt")
        if p.name.lower() != "recibido.txt"
    ]
    if not txt_files:
        raise RuntimeError(f"No se encontró ningún archivo .txt en {tests_dir}")

    # Tomamos el primero
    return txt_files[0]"""


# ----------------- USB helpers para RX (NUEVO) -----------------
def find_usb_mount_rx():
    """
    Devuelve la carpeta donde está montada la USB en el nodo RX.
    Asume Raspberry Pi OS que monta en /media/<usuario>/<LABEL>.
    """
    user = Path.home().name
    media_root = Path("/media") / user

    if not media_root.exists():
        raise RuntimeError(f"[RX] No se encontró la carpeta {media_root} (¿USB sin montar?)")

    mounts = [d for d in media_root.iterdir() if d.is_dir()]
    if not mounts:
        raise RuntimeError(f"[RX] No se encontró ninguna USB montada en {media_root}")

    # Como solo habrá una USB, tomamos la primera
    return mounts[0]


def get_dest_usb_path_rx(filename="recibido.txt"):
    """
    Devuelve la ruta donde se guardará el archivo recibido en la USB.
    Ejemplo: /media/<user>/<LABEL>/recibido.txt
    """
    mount = find_usb_mount_rx()
    return mount / filename


# ----------------- USB helpers (para TX) -----------------
def find_usb_mount():
    """
    Devuelve la carpeta donde está montada la USB.
    Asume Raspberry Pi OS que monta en /media/<usuario>/<LABEL>.
    """
    user = Path.home().name
    media_root = Path("/media") / user

    if not media_root.exists():
        raise RuntimeError(f"No se encontró la carpeta {media_root} (¿USB sin montar?)")

    mounts = [d for d in media_root.iterdir() if d.is_dir()]
    if not mounts:
        raise RuntimeError(f"No se encontró ninguna USB montada en {media_root}")

    # Como solo habrá una USB, tomamos la primera
    return mounts[0]


def find_source_txt_file():
    """
    Busca el primer archivo .txt en la USB.
    Se asume que la llave solo tendrá un archivo .txt.
    """
    mount = find_usb_mount()
    txt_files = list(mount.glob("*.txt"))
    if not txt_files:
        raise RuntimeError(f"No se encontró ningún archivo .txt en {mount}")
    return txt_files[0]



def wait_for_button_choice():
    """
    Espera a que se presione TX o RX.
    Devuelve 'tx' o 'rx'.
    """
    print("\n[MAIN] Pulsa botón TX o RX para seleccionar modo...")
    print("       (TX = GPIO23, RX = GPIO24)")

    while True:
        # Botones con pull-up -> reposo = 1, presionado = 0
        if GPIO.input(BTN_TX) == GPIO.LOW:
            time.sleep(0.05)  # debounce
            if GPIO.input(BTN_TX) == GPIO.LOW:
                print("[MAIN] Botón TX detectado.")
                while GPIO.input(BTN_TX) == GPIO.LOW:
                    time.sleep(0.01)
                return "tx"

        if GPIO.input(BTN_RX) == GPIO.LOW:
            time.sleep(0.05)
            if GPIO.input(BTN_RX) == GPIO.LOW:
                print("[MAIN] Botón RX detectado.")
                while GPIO.input(BTN_RX) == GPIO.LOW:
                    time.sleep(0.01)
                return "rx"

        time.sleep(0.01)


# ----------------- TX: enviar archivo -----------------
def send_file_over_radio(path: Path):
    """
    Envía el archivo indicado vía nRF24 en bloques de 32 bytes.
    Mientras envía, hace parpadear el LED1.
    Devuelve True si todo salió bien, False si hubo error.
    """
    data = path.read_bytes()
    file_size = len(data)
    crc = zlib.crc32(data) & 0xFFFFFFFF

    print(f"[TX] Archivo: {path}")
    print(f"[TX] Tamaño: {file_size} bytes, CRC32: {crc:08X}")

    # Construir cabecera: "HDR" + file_size (4 bytes) + crc32 (4 bytes) + relleno
    header = HEADER_PREFIX + struct.pack("<II", file_size, crc)
    header = header.ljust(CHUNK_SIZE, b"\x00")

    radio.stopListening()

    # Enviar cabecera
    print("[TX] Enviando cabecera...")
    ok = False    # <-- aquí necesitamos ok
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

    # LED1 encendido al finalizar
    GPIO.output(LED1, GPIO.HIGH)
    GPIO.output(LED2, GPIO.LOW)
    return True


def modo_tx():
    """
    Modo transmisor:
    - LED1 parpadea mientras envía el archivo .txt desde la USB.
    - Al terminar, LED1 queda encendido, LED2 apagado.
    """
    print("Entrando a modo TX...")
    GPIO.output(LED2, GPIO.LOW)

    try:
        source_path = find_source_txt_file()
    except Exception as e:
        print(f"[TX] ERROR buscando archivo en USB: {e}")
        blink_error()
        GPIO.output(LED1, GPIO.HIGH)
        GPIO.output(LED2, GPIO.LOW)
        return

    ok = send_file_over_radio(source_path)
    if not ok:
        print("[TX] Transmisión fallida.")
        blink_error()
    else:
        print("[TX] Transmisión exitosa.")

    GPIO.output(LED1, GPIO.HIGH)
    GPIO.output(LED2, GPIO.LOW)


# ----------------- RX: recibir archivo -----------------
def receive_file_over_radio(dest_path, header_timeout_s=10, data_timeout_s=2):
    """
    Recibe un archivo vía nRF24 y lo guarda en dest_path.
    LED1 apagado, LED2 encendido mientras espera/recibe.
    Devuelve True si todo salió bien, False si hubo error.
    """
    print(f"[RX] Guardará archivo en: {dest_path}")

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
                print("[RX] Paquete sin 'HDR' ignorado.")
                continue

            try:
                file_size, crc_expected = struct.unpack("<II", packet[3:11])
            except struct.error:
                print("[RX] ERROR: cabecera mal formada.")
                radio.stopListening()
                GPIO.output(LED2, GPIO.LOW)
                return False

            print(f"[RX] Cabecera: tamaño={file_size} bytes, CRC32={crc_expected:08X}")
            break

        if time.time() - start > header_timeout_s:
            print("[RX] ERROR: timeout esperando cabecera.")
            radio.stopListening()
            GPIO.output(LED2, GPIO.LOW)
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
                GPIO.output(LED2, GPIO.LOW)
                return False
            time.sleep(0.005)

    radio.stopListening()

    data = bytes(received[:file_size])

    # Verificar CRC
    crc_calc = zlib.crc32(data) & 0xFFFFFFFF
    if crc_calc != crc_expected:
        print(f"[RX] ERROR CRC: esperado {crc_expected:08X}, calculado {crc_calc:08X}")
        GPIO.output(LED2, GPIO.LOW)
        return False

    dest_path.write_bytes(data)
    print(f"[RX] Archivo recibido y guardado correctamente ({file_size} bytes).")

    GPIO.output(LED2, GPIO.LOW)
    GPIO.output(LED1, GPIO.HIGH)
    return True


def modo_rx(timeout_s=60):
    """
    Modo receptor:
    - LED1 se apaga, LED2 se enciende.
    - Espera archivo y lo guarda como recibido.txt.
      Puedes elegir entre guardarlo localmente o en la USB.
    """
    print("Entrando a modo RX...")

    # Opción 1: guardar localmente en la carpeta del script
    base_dir = Path(__file__).resolve().parent
    dest_path = base_dir / "recibido.txt"

    # Opción 2: guardar en la USB
    #dest_path = get_dest_usb_path_rx("recibido.txt")

    ok = receive_file_over_radio(dest_path,
                                 header_timeout_s=timeout_s,
                                 data_timeout_s=2)

    if not ok:
        print("[RX] Recepción fallida.")
        blink_error()
    else:
        print(f"[RX] Recepción OK. Archivo guardado en: {dest_path}")

    GPIO.output(LED1, GPIO.HIGH)
    GPIO.output(LED2, GPIO.LOW)


# ----------------- Programa principal -----------------
def main():
    setup_gpio()
    setup_radio()

    # Estado inicial: LED1 encendido, LED2 apagado
    GPIO.output(LED1, GPIO.HIGH)
    GPIO.output(LED2, GPIO.LOW)
    print("[MAIN] Nodo listo. LED1 encendido (idle).")

    while True:
        choice = wait_for_button_choice()

        if choice == "tx":
            modo_tx()
        elif choice == "rx":
            modo_rx(timeout_s=60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nSaliendo por Ctrl+C...")
    finally:
        GPIO.cleanup()
