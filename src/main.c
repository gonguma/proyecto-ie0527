#include <RF24/RF24.h>
#include <pigpio.h>

#include <iostream>
#include <fstream>
#include <cstring>
#include <thread>
#include <chrono>

// -------------------- Definición de pines --------------------

// GPIO Raspberry Pi (números BCM)
constexpr int PIN_CE   = 22;  // CE del nRF24
constexpr int PIN_CSN  = 8;   // CSN del nRF24 (SPI CE0)
constexpr int PIN_LED  = 17;  // LED de estado
constexpr int PIN_BTN  = 27;  // Botón
constexpr int PIN_SW   = 23;  // Switch modo TX/RX

// Archivos (ajusta las rutas a tu montaje de USB)
const std::string TX_FILE = "/home/pi/tx/texto.txt";
const std::string RX_FILE = "/home/pi/rx/recibido.txt";

// -------------------- Radio RF24 --------------------

RF24 radio(PIN_CE, PIN_CSN);

// Dos direcciones para diferenciar nodos
// address[0] = esta placa cuando es "Nodo A"
// address[1] = esta placa cuando es "Nodo B"
const uint8_t address[][6] = {"1Node", "2Node"};

// Para saber quién soy en esta ejecución
int thisNodeIndex = 0;   // 0 o 1
int otherNodeIndex = 1;

// -------------------- Estructura de paquete --------------------

#define TIPO_HEADER  0x01
#define TIPO_DATA    0x02
#define TIPO_FIN     0x03

#pragma pack(push, 1)
struct Paquete {
    uint8_t  tipo;        // 1 = header, 2 = data, 3 = fin
    uint32_t seq;         // header: tamaño archivo / fin: nº bloques / data: nº bloque
    uint8_t  data[27];    // datos o info extra
};
#pragma pack(pop)

// -------------------- Helpers de tiempo --------------------

void sleep_ms(int ms) {
    std::this_thread::sleep_for(std::chrono::milliseconds(ms));
}

// -------------------- Manejo del LED --------------------

void led_on() {
    gpioWrite(PIN_LED, 1);
}

void led_off() {
    gpioWrite(PIN_LED, 0);
}

void led_toggle() {
    int val = gpioRead(PIN_LED);
    gpioWrite(PIN_LED, !val);
}

// Parpadeo lento mientras se ejecuta una sección bloqueante
// Aquí usaremos un truco: la función que envía/recibe llamará led_toggle()
// cada cierto número de paquetes, en lugar de un hilo separado.

// -------------------- GPIO: botón y switch --------------------

bool boton_presionado() {
    // Recordar que BTN está con pull-up: 1 = suelto, 0 = presionado
    return (gpioRead(PIN_BTN) == 0);
}

// Lee el modo a partir del switch:
// 0 = MODO ENVÍO, 1 = MODO RECEPCIÓN
int leer_modo() {
    int val = gpioRead(PIN_SW); // dependerá de cómo cableaste el switch
    // Supongamos: SW a GND => 0 (ENVÍO), SW a 3.3V => 1 (RECEPCIÓN)
    return val ? 1 : 0;
}

// -------------------- Inicialización GPIO y radio --------------------

bool init_gpio() {
    if (gpioInitialise() < 0) {
        std::cerr << "Error inicializando pigpio\n";
        return false;
    }

    // LED como salida
    gpioSetMode(PIN_LED, PI_OUTPUT);
    gpioWrite(PIN_LED, 0);

    // Botón y switch como entradas
    gpioSetMode(PIN_BTN, PI_INPUT);
    gpioSetMode(PIN_SW, PI_INPUT);

    // Pull-ups (botón y switch)
    gpioSetPullUpDown(PIN_BTN, PI_PUD_UP);
    gpioSetPullUpDown(PIN_SW, PI_PUD_UP);

    return true;
}

// modoEnvio == true => esta placa será el "Nodo A" (dirección address[0] enviando a address[1])
// modoEnvio == false => esta placa será el "Nodo B" (receptor principal)
bool init_radio(bool modoEnvio) {

    if (!radio.begin()) {
        std::cerr << "Error inicializando radio nRF24\n";
        return false;
    }

    // Ajustes básicos
    radio.setChannel(76);                   // canal en 2.4 GHz (76 es típico de ejemplo)
    radio.setDataRate(RF24_250KBPS);        // más robusto, suficiente para 2 kB
    radio.setPALevel(RF24_PA_MAX);          // máxima potencia (cuidado con interferencias cercanas)
    radio.setRetries(5, 15);                // reintentos automáticos

    if (modoEnvio) {
        // Esta placa será "Nodo A"
        thisNodeIndex  = 0;
        otherNodeIndex = 1;

        // Escribimos hacia la dirección del otro nodo
        radio.openWritingPipe(address[otherNodeIndex]);
        // Abrimos canal de lectura por si queremos recibir algo (opcional)
        radio.openReadingPipe(1, address[thisNodeIndex]);

        radio.stopListening(); // por defecto en TX
    } else {
        // Esta placa será "Nodo B"
        thisNodeIndex  = 1;
        otherNodeIndex = 0;

        // Escribimos hacia el nodo A (por si algún día mandamos ACKs explícitos)
        radio.openWritingPipe(address[otherNodeIndex]);
        // Leemos en nuestra propia dirección
        radio.openReadingPipe(1, address[thisNodeIndex]);

        radio.startListening(); // por defecto en RX
    }

    return true;
}

// -------------------- Envío de archivo --------------------

bool enviar_archivo(const std::string &ruta) {

    std::ifstream fin(ruta, std::ios::binary);
    if (!fin.is_open()) {
        std::cerr << "No se pudo abrir archivo TX: " << ruta << "\n";
        return false;
    }

    // Calcular tamaño
    fin.seekg(0, std::ios::end);
    long tam = fin.tellg();
    fin.seekg(0, std::ios::beg);

    if (tam <= 0) {
        std::cerr << "Archivo vacio o error de tamaño\n";
        return false;
    }

    std::cout << "Enviando archivo de " << tam << " bytes\n";

    // 1) Enviar HEADER
    Paquete p;
    std::memset(&p, 0, sizeof(p));
    p.tipo = TIPO_HEADER;
    p.seq  = static_cast<uint32_t>(tam);  // usamos seq para enviar tamaño

    radio.stopListening(); // asegurarnos que estamos en modo TX

    bool ok = radio.write(&p, sizeof(p));
    if (!ok) {
        std::cerr << "Fallo al enviar HEADER\n";
        return false;
    }

    // 2) Enviar DATA
    uint32_t seq = 0;
    const size_t DATA_BYTES = sizeof(p.data); // 27
    size_t enviadosTotal = 0;

    while (enviadosTotal < static_cast<size_t>(tam)) {

        std::memset(&p, 0, sizeof(p));
        p.tipo = TIPO_DATA;
        p.seq  = seq;

        // Leer siguiente bloque del archivo
        fin.read(reinterpret_cast<char*>(p.data), DATA_BYTES);
        std::streamsize leidos = fin.gcount();
        if (leidos <= 0) {
            break; // debería ser exactamente el final
        }

        // Enviar paquete
        ok = radio.write(&p, sizeof(p));
        if (!ok) {
            std::cerr << "Fallo al enviar DATA, bloque " << seq << "\n";
            return false;
        }

        enviadosTotal += static_cast<size_t>(leidos);
        seq++;

        // Hacer parpadear el LED lento (por ejemplo, cada 4 bloques)
        if (seq % 4 == 0) {
            led_toggle();
        }
    }

    fin.close();

    // 3) Enviar FIN
    std::memset(&p, 0, sizeof(p));
    p.tipo = TIPO_FIN;
    p.seq  = seq; // número total de bloques enviados

    ok = radio.write(&p, sizeof(p));
    if (!ok) {
        std::cerr << "Fallo al enviar FIN\n";
        return false;
    }

    // Dejar LED encendido fijo al terminar
    led_on();

    std::cout << "Archivo enviado, bloques: " << seq << "\n";
    return true;
}

// -------------------- Recepción de archivo --------------------

bool recibir_archivo(const std::string &rutaOut) {

    // Asegurar que estamos en modo escucha
    radio.startListening();

    Paquete p;
    std::memset(&p, 0, sizeof(p));

    bool headerRecibido = false;
    uint32_t tamEsperado = 0;
    uint32_t bloquesEsperados = 0;
    uint32_t bloquesRecibidos = 0;

    std::ofstream fout;

    std::cout << "Esperando archivo...\n";

    while (true) {

        // Esperar hasta que haya datos
        while (!radio.available()) {
            sleep_ms(5);
        }

        radio.read(&p, sizeof(p));

        if (p.tipo == TIPO_HEADER) {

            // Cambiar patrón de LED: parpadeo lento
            led_toggle(); // inicio de recepción

            tamEsperado = p.seq; // en este ejemplo, tamaño viene en seq
            const uint32_t DATA_BYTES = sizeof(p.data);
            bloquesEsperados = (tamEsperado + DATA_BYTES - 1) / DATA_BYTES;

            std::cout << "HEADER recibido. Tam: " << tamEsperado
                      << " bytes, bloques esperados: " << bloquesEsperados << "\n";

            // Abrir archivo de salida
            fout.open(rutaOut, std::ios::binary);
            if (!fout.is_open()) {
                std::cerr << "No se pudo abrir archivo RX: " << rutaOut << "\n";
                return false;
            }

            headerRecibido = true;
            bloquesRecibidos = 0;
        }
        else if (p.tipo == TIPO_DATA && headerRecibido) {

            // Escribir bloque
            fout.write(reinterpret_cast<const char*>(p.data), sizeof(p.data));
            bloquesRecibidos++;

            // Parpadeo lento cada 4 bloques
            if (bloquesRecibidos % 4 == 0) {
                led_toggle();
            }
        }
        else if (p.tipo == TIPO_FIN && headerRecibido) {

            // Cerrar archivo y truncar a tamaño real (porque el último bloque puede venir relleno)
            fout.flush();
            fout.close();

            // Truncar a tamEsperado (opcional pero recomendable)
            std::ofstream truncFile(rutaOut, std::ios::in | std::ios::out | std::ios::binary);
            if (truncFile.is_open()) {
                truncFile.seekp(tamEsperado, std::ios::beg);
                truncFile.flush();
                truncFile.close();
            }

            // Dejar LED fijo
            led_on();

            std::cout << "Archivo recibido. Bloques: " << bloquesRecibidos << "\n";
            return true;
        }
        else {
            // Paquete inesperado; podrías manejar errores aquí
            std::cerr << "Paquete inesperado tipo " << (int)p.tipo << "\n";
        }
    }

    return false;
}

// -------------------- Modos de operación --------------------

void modo_envio() {
    std::cout << "Modo ENVIO\n";

    while (true) {
        if (boton_presionado()) {
            std::cout << "Boton presionado, iniciando envio...\n";

            // esperar a que se suelte, para evitar rebote
            while (boton_presionado()) {
                sleep_ms(20);
            }

            // LED fijo antes de comenzar
            led_on();

            bool ok = enviar_archivo(TX_FILE);

            if (!ok) {
                std::cerr << "Error en envio, LED parpadeo rapido\n";
                // Parpadeo rapido
                for (int i = 0; i < 10; ++i) {
                    led_toggle();
                    sleep_ms(100);
                }
                led_off();
            } else {
                // Dejar LED fijo
                led_on();
            }
        }

        sleep_ms(50);
    }
}

void modo_recepcion() {
    std::cout << "Modo RECEPCION\n";

    while (true) {
        // Aquí podrías estar simplemente escuchando y, cuando
        // llegue un HEADER, recibir_archivo() se encarga de todo.
        bool ok = recibir_archivo(RX_FILE);

        if (!ok) {
            std::cerr << "Error en recepcion, LED parpadeo rapido\n";
            for (int i = 0; i < 10; ++i) {
                led_toggle();
                sleep_ms(100);
            }
            led_off();
        } else {
            // Dejar LED fijo hasta que llegue otro archivo
            led_on();
        }

        // Después de recibir un archivo, seguimos esperando el siguiente
        sleep_ms(200);
    }
}

// -------------------- main --------------------

int main() {

    if (!init_gpio()) {
        return 1;
    }

    // Encender LED para indicar que el programa inició
    led_on();

    // Leer el modo desde el switch
    int modo = leer_modo();  // 0 = ENVIO, 1 = RECEPCION
    bool esEnvio = (modo == 0);

    if (!init_radio(esEnvio)) {
        gpioTerminate();
        return 1;
    }

    std::cout << "Programa iniciado. Modo = "
              << (esEnvio ? "ENVIO" : "RECEPCION") << "\n";

    // LED encendido fijo = listo
    led_on();

    if (esEnvio) {
        modo_envio();
    } else {
        modo_recepcion();
    }

    gpioTerminate();
    return 0;
}
