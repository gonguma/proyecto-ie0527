#!/usr/bin/env python3
import struct
import zlib
from pathlib import Path
import time
import sys

import RPi.GPIO as GPIO
from pyrf24 import RF24, RF24_PA_MAX, RF24_250KBPS, RF24_DRIVER

# ----------------- Pines (BCM) -----------------
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


# ----------------- GPIO -----------------
def setup_gpio():
    GPIO.setmode(GPIO.BCM)

    GPIO.setup(LED1, GPIO.OUT)
    GPIO.setup(LED2, GPIO.OUT)

    GPIO.output(LED1, GPIO.LOW)
    GPIO.output(LED2, GPIO.LOW)


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

    # Solo TX: abrimos pipe de escritura
    radio.openWritingPipe(ADDRESS)
    # Pipe de lectura no es estrictamente necesario en este TX-only
    # pero lo dejamos apagado:
    radio.stopListening()

    print("Radio inicializado correctamente.")
    try:
        print("radio.is_chip_connected =", radio.is_chip_connected)
    except Exception:
        pass


# ----------------- Utilidades -----------------
def blink_error(times=3, delay=0.2):
    for _ in range(times):
        GPIO.output(LED1, GPIO.LOW)
        GPIO.output(LED2, GPIO.HIGH)
        time.sleep(delay)
        GPIO.output(LED1, GPIO.HIGH)
        GPIO.output(LED2, GPIO.LOW)
        time.sleep(delay)


def find_source_txt_file():
    """
    Busca el primer archivo .txt en la carpeta tests,
    que debe estar en el mismo directorio que este script.
    Ej: /home/pi/nodo_rf/tests/archivo.txt
    """
    base_dir = Path(__file__).resolve().parent
    tests_dir = base_dir / "tests"

    if not tests_dir.exists():
        raise RuntimeError(f"No existe la carpeta {tests_dir}")

    txt_files = list(tests_dir.glob("*.txt"))
    if not txt_files:
        raise RuntimeError(f"No se encontró ningún archivo .txt en {tests_dir}")

    # Tomamos el primero
    return txt_files[0]


# ----------------- Enviar archivo -----------------
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


# ----------------- Lógica de modo RX -----------------
def modo_rx(timeout_s=10):
    """
    Modo receptor:
    - Apaga LED1, enciende LED2.
    - Espera archivo desde el otro nodo y lo guarda en la USB como recibido.txt.
    - Al terminar (bien o mal), LED2 OFF, LED1 ON.
    """
    print("Entrando a modo RX...")

    # Carpeta donde está este script (normalmente /home/pi/nodo_rf)
    base_dir = Path(__file__).resolve().parent
    dest_path = base_dir / "recibido.txt"

    print(f"[RX] Guardará archivo en: {dest_path}")

    ok = receive_file_over_radio(dest_path,
                                 header_timeout_s=timeout_s,
                                 data_timeout_s=2)

    if not ok:
        print("[RX] Recepción fallida.")
        blink_error()
    else:
        print("[RX] Recepción exitosa.")

    # Volvemos a "idle": LED1 ON, LED2 OFF
    GPIO.output(LED1, GPIO.HIGH)
    GPIO.output(LED2, GPIO.LOW)


# ----------------- Modo TX (una sola vez) -----------------
def modo_tx():
    """
    - LED1 parpadea mientras envía.
    - Al terminar:
      - si éxito: LED1 queda encendido.
      - si error: parpadeo de error.
    """
    GPIO.output(LED2, GPIO.LOW)

    try:
        source_path = find_source_txt_file()
    except Exception as e:
        print(f"[TX] ERROR buscando archivo en tests/: {e}")
        blink_error()
        GPIO.output(LED1, GPIO.LOW)
        GPIO.output(LED2, GPIO.LOW)
        return

    ok = send_file_over_radio(source_path)
    if not ok:
        print("[TX] Transmisión fallida.")
        blink_error()
    else:
        print("[TX] Transmisión exitosa.")

    # Estado final: LED1 encendido, LED2 apagado
    GPIO.output(LED1, GPIO.HIGH)
    GPIO.output(LED2, GPIO.LOW)


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
