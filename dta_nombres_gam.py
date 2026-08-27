from __future__ import annotations

import re
import unicodedata


def _norm(value: object) -> str:
    text = "" if value is None else str(value).strip()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", text).upper()


PROVINCES = {
    "SAN JOSE": "San José",
    "ALAJUELA": "Alajuela",
    "CARTAGO": "Cartago",
    "HEREDIA": "Heredia",
    "GUANACASTE": "Guanacaste",
    "PUNTARENAS": "Puntarenas",
    "LIMON": "Limón",
}

PROVINCE_CODES = {
    "SAN JOSE": "1",
    "ALAJUELA": "2",
    "CARTAGO": "3",
    "HEREDIA": "4",
    "GUANACASTE": "5",
    "PUNTARENAS": "6",
    "LIMON": "7",
}

CANTONS = {
    ("1", "1"): "San José", ("1", "2"): "Escazú", ("1", "3"): "Desamparados",
    ("1", "6"): "Aserrí", ("1", "7"): "Mora", ("1", "8"): "Goicoechea",
    ("1", "9"): "Santa Ana", ("1", "10"): "Alajuelita", ("1", "11"): "Vázquez de Coronado",
    ("1", "12"): "Acosta", ("1", "13"): "Tibás", ("1", "14"): "Moravia",
    ("1", "15"): "Montes de Oca", ("1", "18"): "Curridabat",
    ("2", "1"): "Alajuela", ("2", "3"): "Grecia", ("2", "8"): "Poás",
    ("3", "1"): "Cartago", ("3", "2"): "Paraíso", ("3", "3"): "La Unión",
    ("3", "7"): "Oreamuno", ("3", "8"): "El Guarco",
    ("4", "1"): "Heredia", ("4", "2"): "Barva", ("4", "3"): "Santo Domingo",
    ("4", "4"): "Santa Bárbara", ("4", "5"): "San Rafael", ("4", "6"): "San Isidro",
    ("4", "7"): "Belén", ("4", "8"): "Flores", ("4", "9"): "San Pablo",
}

DISTRICTS = {
    # San José
    ("1","1","1"):"Carmen", ("1","1","2"):"Merced", ("1","1","3"):"Hospital",
    ("1","1","4"):"Catedral", ("1","1","5"):"Zapote", ("1","1","6"):"San Francisco de Dos Ríos",
    ("1","1","7"):"Uruca", ("1","1","8"):"Mata Redonda", ("1","1","9"):"Pavas",
    ("1","1","10"):"Hatillo", ("1","1","11"):"San Sebastián",
    ("1","2","1"):"Escazú", ("1","2","2"):"San Antonio", ("1","2","3"):"San Rafael",
    ("1","3","1"):"Desamparados", ("1","3","2"):"San Miguel", ("1","3","3"):"San Juan de Dios",
    ("1","3","4"):"San Rafael Arriba", ("1","3","5"):"San Antonio", ("1","3","6"):"Frailes",
    ("1","3","7"):"Patarrá", ("1","3","8"):"San Cristóbal", ("1","3","9"):"Rosario",
    ("1","3","10"):"Damas", ("1","3","11"):"San Rafael Abajo", ("1","3","12"):"Gravilias",
    ("1","3","13"):"Los Guido",
    ("1","6","1"):"Aserrí", ("1","6","2"):"Tarbaca", ("1","6","3"):"Vuelta de Jorco",
    ("1","6","4"):"San Gabriel", ("1","6","5"):"Legua", ("1","6","6"):"Monterrey",
    ("1","6","7"):"Salitrillos",
    ("1","7","1"):"Colón", ("1","7","2"):"Guayabo", ("1","7","3"):"Tabarcia",
    ("1","7","4"):"Piedras Negras", ("1","7","5"):"Picagres", ("1","7","6"):"Jaris",
    ("1","8","1"):"Guadalupe", ("1","8","2"):"San Francisco", ("1","8","3"):"Calle Blancos",
    ("1","8","4"):"Mata de Plátano", ("1","8","5"):"Ipís", ("1","8","6"):"Rancho Redondo",
    ("1","8","7"):"Purral",
    ("1","9","1"):"Santa Ana", ("1","9","2"):"Salitral", ("1","9","3"):"Pozos",
    ("1","9","4"):"Uruca", ("1","9","5"):"Piedades", ("1","9","6"):"Brasil",
    ("1","10","1"):"Alajuelita", ("1","10","2"):"San Josecito", ("1","10","3"):"San Antonio",
    ("1","10","4"):"Concepción", ("1","10","5"):"San Felipe",
    ("1","11","1"):"San Isidro", ("1","11","2"):"San Rafael", ("1","11","3"):"Dulce Nombre de Jesús",
    ("1","11","4"):"Patalillo", ("1","11","5"):"Cascajal",
    ("1","12","1"):"San Ignacio", ("1","12","2"):"Guaitil", ("1","12","3"):"Palmichal",
    ("1","12","4"):"Cangrejal", ("1","12","5"):"Sabanillas",
    ("1","13","1"):"San Juan", ("1","13","2"):"Cinco Esquinas", ("1","13","3"):"Anselmo Llorente",
    ("1","13","4"):"León XIII", ("1","13","5"):"Colima",
    ("1","14","1"):"San Vicente", ("1","14","2"):"San Jerónimo", ("1","14","3"):"La Trinidad",
    ("1","15","1"):"San Pedro", ("1","15","2"):"Sabanilla", ("1","15","3"):"Mercedes",
    ("1","15","4"):"San Rafael",
    ("1","18","1"):"Curridabat", ("1","18","2"):"Granadilla", ("1","18","3"):"Sánchez",
    ("1","18","4"):"Tirrases",

    # Alajuela
    ("2","1","1"):"Alajuela", ("2","1","2"):"San José", ("2","1","3"):"Carrizal",
    ("2","1","4"):"San Antonio", ("2","1","5"):"Guácima", ("2","1","6"):"San Isidro",
    ("2","1","7"):"Sabanilla", ("2","1","8"):"San Rafael", ("2","1","9"):"Río Segundo",
    ("2","1","10"):"Desamparados", ("2","1","11"):"Turrúcares", ("2","1","12"):"Tambor",
    ("2","1","13"):"Garita", ("2","1","14"):"Sarapiquí",
    ("2","3","1"):"Grecia", ("2","3","2"):"San Isidro", ("2","3","3"):"San José",
    ("2","3","4"):"San Roque", ("2","3","5"):"Tacares", ("2","3","6"):"Río Cuarto",
    ("2","3","7"):"Puente de Piedra", ("2","3","8"):"Bolívar",
    ("2","8","1"):"San Pedro", ("2","8","2"):"San Juan", ("2","8","3"):"San Rafael",
    ("2","8","4"):"Carrillos", ("2","8","5"):"Sabana Redonda",

    # Cartago
    ("3","1","1"):"Oriental", ("3","1","2"):"Occidental", ("3","1","3"):"Carmen",
    ("3","1","4"):"San Nicolás", ("3","1","5"):"Aguacaliente (San Francisco)",
    ("3","1","6"):"Guadalupe (Arenilla)", ("3","1","7"):"Corralillo", ("3","1","8"):"Tierra Blanca",
    ("3","1","9"):"Dulce Nombre", ("3","1","10"):"Llano Grande", ("3","1","11"):"Quebradilla",
    ("3","2","1"):"Paraíso", ("3","2","2"):"Santiago", ("3","2","3"):"Orosi",
    ("3","2","4"):"Cachí", ("3","2","5"):"Llanos de Santa Lucía",
    ("3","3","1"):"Tres Ríos", ("3","3","2"):"San Diego", ("3","3","3"):"San Juan",
    ("3","3","4"):"San Rafael", ("3","3","5"):"Concepción", ("3","3","6"):"Dulce Nombre",
    ("3","3","7"):"San Ramón", ("3","3","8"):"Río Azul",
    ("3","7","1"):"San Rafael", ("3","7","2"):"Cot", ("3","7","3"):"Potrero Cerrado",
    ("3","7","4"):"Cipreses", ("3","7","5"):"Santa Rosa",
    ("3","8","1"):"El Tejar", ("3","8","2"):"San Isidro", ("3","8","3"):"Tobosi",
    ("3","8","4"):"Patio de Agua",

    # Heredia
    ("4","1","1"):"Heredia", ("4","1","2"):"Mercedes", ("4","1","3"):"San Francisco",
    ("4","1","4"):"Ulloa", ("4","1","5"):"Varablanca",
    ("4","2","1"):"Barva", ("4","2","2"):"San Pedro", ("4","2","3"):"San Pablo",
    ("4","2","4"):"San Roque", ("4","2","5"):"Santa Lucía", ("4","2","6"):"San José de la Montaña",
    ("4","3","1"):"Santo Domingo", ("4","3","2"):"San Vicente", ("4","3","3"):"San Miguel",
    ("4","3","4"):"Paracito", ("4","3","5"):"Santo Tomás", ("4","3","6"):"Santa Rosa",
    ("4","3","7"):"Tures", ("4","3","8"):"Pará",
    ("4","4","1"):"Santa Bárbara", ("4","4","2"):"San Pedro", ("4","4","3"):"San Juan",
    ("4","4","4"):"Jesús", ("4","4","5"):"Santo Domingo", ("4","4","6"):"Purabá",
    ("4","5","1"):"San Rafael", ("4","5","2"):"San Josecito", ("4","5","3"):"Santiago",
    ("4","5","4"):"Los Ángeles", ("4","5","5"):"Concepción",
    ("4","6","1"):"San Isidro", ("4","6","2"):"San José", ("4","6","3"):"Concepción",
    ("4","6","4"):"San Francisco",
    ("4","7","1"):"San Antonio", ("4","7","2"):"La Ribera", ("4","7","3"):"La Asunción",
    ("4","8","1"):"San Joaquín de Flores", ("4","8","2"):"Barrantes", ("4","8","3"):"Llorente",
    ("4","9","1"):"San Pablo", ("4","9","2"):"Rincón de Sabanilla",
}


def province_name(raw_province: object) -> str:
    normalized = _norm(raw_province)
    return PROVINCES.get(normalized, str(raw_province).strip().title())


def province_code(raw_province: object) -> str:
    return PROVINCE_CODES.get(_norm(raw_province), "")


def canton_name(raw_province: object, raw_canton: object) -> str:
    p = province_code(raw_province)
    c = str(raw_canton).strip().lstrip("0") or "0"
    return CANTONS.get((p, c), f"Cantón {c}")


def district_name(raw_province: object, raw_canton: object, raw_district: object) -> str:
    p = province_code(raw_province)
    c = str(raw_canton).strip().lstrip("0") or "0"
    d = str(raw_district).strip().lstrip("0") or "0"
    return DISTRICTS.get((p, c, d), f"Distrito {d}")
