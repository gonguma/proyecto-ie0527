# Makefile para compilar src/main.c en Raspberry Pi Zero W
# Usa las librerías RF24 y pigpio

# Compilador (usamos g++ porque el código es estilo C++)
CXX      = g++
CXXFLAGS = -std=c++17 -Wall -Wextra -O2

# Directorios
SRC_DIR  = src
OBJ_DIR  = build

# Archivos fuente / objeto / binario
SRCS   = $(SRC_DIR)/main.c
OBJS   = $(OBJ_DIR)/main.o
TARGET = main

# Librerías a enlazar
LDLIBS = -lrf24 -lpigpio -lrt -lpthread

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LDLIBS)

# Regla genérica para compilar .c -> .o dentro de build/
$(OBJ_DIR)/%.o: $(SRC_DIR)/%.c
	@mkdir -p $(OBJ_DIR)
	$(CXX) $(CXXFLAGS) -c $< -o $@

clean:
	rm -rf $(OBJ_DIR) $(TARGET)

.PHONY: all clean
