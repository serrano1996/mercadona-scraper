BASE_URL = "https://tienda.mercadona.es"
API_URL = "https://tienda.mercadona.es/api"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9",
    "Referer": "https://tienda.mercadona.es/",
    "Origin": "https://tienda.mercadona.es",
}

# Mapeo de prefijos de código postal (2 dígitos) → identificador de almacén Mercadona
POSTAL_TO_WH: dict[str, str] = {
    "01": "bil1", "02": "vlc1", "03": "alc1", "04": "vlc1", "05": "mad1",
    "06": "vlc1", "07": "vlc1", "08": "bcn1", "09": "bil1", "10": "mad1",
    "11": "svq1", "12": "vlc1", "13": "mad1", "14": "svq1", "15": "vlc1",
    "16": "mad1", "17": "bcn1", "18": "vlc1", "19": "mad1", "20": "bil1",
    "21": "svq1", "22": "zar1", "23": "vlc1", "24": "mad1", "25": "bcn1",
    "26": "bil1", "27": "vlc1", "28": "mad1", "29": "vlc1", "30": "alc1",
    "31": "bil1", "32": "vlc1", "33": "vlc1", "34": "mad1", "35": "vlc1",
    "36": "vlc1", "37": "mad1", "38": "vlc1", "39": "bil1", "40": "mad1",
    "41": "svq1", "42": "mad1", "43": "bcn1", "44": "zar1", "45": "mad1",
    "46": "vlc1", "47": "mad1", "48": "bil1", "49": "mad1", "50": "zar1",
    "51": "mad1", "52": "mad1",
}