"""mkvmerge y mkvpropedit de mentira, para el CI, que no tiene mkvtoolnix.

El "MKV" es un JSON con la misma forma que `mkvmerge -J`. mkvpropedit lo
reescribe en el sitio (mismo inodo, bytes distintos) y `mkvmerge -o` escribe uno
nuevo con las pistas en el orden pedido: lo que la subida tiene que vigilar.
"""
import json
import os
import sys


def _leer(ruta):
    with open(ruta, encoding="utf-8") as fh:
        return json.load(fh)


def mkvmerge(args):
    if args[0] == "-J":
        try:
            print(json.dumps(_leer(args[1])))
        except (OSError, ValueError):
            print(json.dumps({"container": {"recognized": False}, "tracks": []}))
        return 0
    salida, datos = args[args.index("-o") + 1], _leer(args[-1])
    por_id, orden = {t["id"]: t for t in datos["tracks"]}, list(range(len(datos["tracks"])))
    for opcion, valor in zip(args, args[1:]):
        if opcion == "--track-name":
            tid, nombre = valor.split(":", 1)
            por_id[int(tid)]["properties"]["track_name"] = nombre
        elif opcion == "--default-track-flag":
            tid, flag = valor.split(":", 1)
            por_id[int(tid)]["properties"]["default_track"] = flag == "1"
        elif opcion == "--track-order":
            orden = [int(x.split(":")[1]) for x in valor.split(",")]
    datos["tracks"] = [dict(por_id[tid], id=n) for n, tid in enumerate(orden)]
    with open(salida, "w", encoding="utf-8") as fh:
        json.dump(datos, fh)
    print("#GUI#progress 50%")
    print("#GUI#progress 100%")
    return 0


def mkvpropedit(args):
    ruta, datos, actual = args[0], _leer(args[0]), None
    por_uid = {t["properties"].get("uid"): t["properties"] for t in datos["tracks"]}
    for opcion, valor in zip(args[1:], args[2:]):
        if opcion == "--edit":
            if valor == "info":
                actual = datos["container"]["properties"]
            elif valor.startswith("track:="):
                actual = por_uid[int(valor.split("=", 1)[1])]
            else:
                actual = datos["tracks"][int(valor.split(":", 1)[1]) - 1]["properties"]
        elif opcion == "--set":
            clave, v = valor.split("=", 1)
            if clave == "flag-default":
                actual["default_track"] = v == "1"
            else:
                actual["track_name" if clave == "name" else clave] = v
    with open(ruta, "r+", encoding="utf-8") as fh:
        json.dump(datos, fh)
        fh.truncate()
    return 0


if __name__ == "__main__":
    programa = os.path.basename(sys.argv[0])
    sys.exit({"mkvmerge": mkvmerge, "mkvpropedit": mkvpropedit}[programa](sys.argv[1:]))
