from __future__ import annotations

import dta_nombres_gam as base

EXTRA_CANTONS = {
    ("1", "4"): "Puriscal",
    ("1", "5"): "Tarrazú",
    ("1", "16"): "Turrubares",
    ("1", "17"): "Dota",
    ("1", "19"): "Pérez Zeledón",
    ("1", "20"): "León Cortés Castro",
}

EXTRA_DISTRICTS = {
    ("1","4","1"):"Santiago", ("1","4","2"):"Mercedes Sur", ("1","4","3"):"Barbacoas",
    ("1","4","4"):"Grifo Alto", ("1","4","5"):"San Rafael", ("1","4","6"):"Candelarita",
    ("1","4","7"):"Desamparaditos", ("1","4","8"):"San Antonio", ("1","4","9"):"Chires",
    ("1","5","1"):"San Marcos", ("1","5","2"):"San Lorenzo", ("1","5","3"):"San Carlos",
    ("1","16","1"):"San Pablo", ("1","16","2"):"San Pedro", ("1","16","3"):"San Juan de Mata",
    ("1","16","4"):"San Luis", ("1","16","5"):"Carara",
    ("1","17","1"):"Santa María", ("1","17","2"):"Jardín", ("1","17","3"):"Copey",
    ("1","19","1"):"San Isidro de El General", ("1","19","2"):"General", ("1","19","3"):"Daniel Flores",
    ("1","19","4"):"Rivas", ("1","19","5"):"San Pedro", ("1","19","6"):"Platanares",
    ("1","19","7"):"Pejibaye", ("1","19","8"):"Cajón", ("1","19","9"):"Barú",
    ("1","19","10"):"Río Nuevo", ("1","19","11"):"Páramo",
    ("1","20","1"):"San Pablo", ("1","20","2"):"San Andrés", ("1","20","3"):"Llano Bonito",
    ("1","20","4"):"San Isidro", ("1","20","5"):"Santa Cruz", ("1","20","6"):"San Antonio",
}


def province_name(raw_province: object) -> str:
    return base.province_name(raw_province)


def canton_name(raw_province: object, raw_canton: object) -> str:
    p = base.province_code(raw_province)
    c = str(raw_canton).strip().lstrip("0") or "0"
    return EXTRA_CANTONS.get((p, c), base.canton_name(raw_province, raw_canton))


def district_name(raw_province: object, raw_canton: object, raw_district: object) -> str:
    p = base.province_code(raw_province)
    c = str(raw_canton).strip().lstrip("0") or "0"
    d = str(raw_district).strip().lstrip("0") or "0"
    return EXTRA_DISTRICTS.get((p, c, d), base.district_name(raw_province, raw_canton, raw_district))
