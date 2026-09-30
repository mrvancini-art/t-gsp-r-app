import argparse
import os
from pathlib import Path
import sys
import time
from datetime import datetime
import requests
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.align import Align
from rich.prompt import Prompt

# Readline-hantering för Tab-komplettering
try:
    import readline
    if "libedit" in (readline.__doc__ or ""):
        readline.parse_and_bind("bind ^I rl_complete")
    else:
        readline.parse_and_bind("tab: complete")
except Exception:
    readline = None

def set_tab_completer(options):
    """Konfigurerar readline tab-komplettering för en lista av alternativ."""
    if not readline:
        return

    options_list = list(options)

    def completer(text, state):
        if not text:
            matches = options_list
        else:
            text_lower = text.lower()
            matches = [opt for opt in options_list if opt.lower().startswith(text_lower)]
            if not matches:
                matches = [opt for opt in options_list if text_lower in opt.lower()]
        if state < len(matches):
            return matches[state]
        return None

    readline.set_completer_delims("")
    readline.set_completer(completer)

def _load_env():
    """Laddar miljövariabler via python-dotenv om tillgängligt, annars inbyggd fallback."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        for env_path in [Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"]:
            if env_path.is_file():
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            os.environ.setdefault(k.strip(), v.strip().strip("'\""))
                break

_load_env()

# --- KONFIGURATION ---
API_KEY = os.environ.get("TRAFIKVERKET_API_KEY")
API_URL = "https://api.trafikinfo.trafikverket.se/v2/data.json"
DEFAULT_UPDATE_INTERVAL = 300  # 5 minuter

console = Console()
last_error = ""
total_trains_fetched = 0

# --- STATIONSKATALOG ---
STATIONS = {
    # Östergötland & närområde
    "Nr": "Norrköping C",
    "Lp": "Linköping C",
    "Kms": "Kimstad",
    "Lgm": "Linghem",
    "Vst": "Vikingstad",
    "Mp": "Mantorp",
    "My": "Mjölby",
    "Tra": "Tranås",
    "Bxm": "Boxholm",
    "Skm": "Skänninge",
    "Mtl": "Motala",

    # Storstäder
    "Cst": "Stockholm C",
    "G": "Göteborg C",
    "M": "Malmö C",
    "U": "Uppsala C",
    "Lu": "Lund C",

    # Mellansverige & Mälardalen
    "Ör": "Örebro C",
    "Öb": "Örebro S",
    "Vå": "Västerås C",
    "Et": "Eskilstuna C",
    "K": "Katrineholm C",
    "Arnc": "Arlanda C",
    "Sub": "Sundbyberg",
    "So": "Solna",
    "Äs": "Älvsjö",
    "Fst": "Flemingsberg",
    "Sö": "Södertälje C",
    "Syd": "Södertälje Syd",
    "Nrk": "Norrviken",
    "Bål": "Bålsta",
    "En": "Enköping",
    "Sl": "Sala",
    "Kp": "Köping",
    "Arb": "Arboga",

    # Södra Sverige & Västkusten
    "Hb": "Helsingborg C",
    "Hd": "Halmstad C",
    "Bs": "Borås C",
    "Jö": "Jönköping C",
    "Vö": "Växjö C",
    "Al": "Alingsås",
    "F": "Falköping C",
    "Sk": "Skövde C",
    "Thn": "Trollhättan C",
    "N": "Nässjö C",
    "Av": "Alvesta",
    "Hp": "Hässleholm C",
    "Kac": "Kalmar C",
    "Ck": "Karlskrona C",
    "Cr": "Kristianstad C",
    "Y": "Ystad",
    "Tle": "Trelleborg",
    "Vb": "Varberg",
    "Kba": "Kungsbacka",

    # Värmland, Dalarna & Norrland
    "Ks": "Karlstad C",
    "Khn": "Kristinehamn",
    "Bor": "Borlänge C",
    "Fal": "Falun C",
    "Mra": "Mora",
    "Gä": "Gävle C",
    "Hvd": "Hudiksvall",
    "Sm": "Söderhamn",
    "Bln": "Bollnäs",
    "Lj": "Ljusdal",
    "Suc": "Sundsvall C",
    "Hno": "Härnösand",
    "Ös": "Östersund C",
    "År": "Åre",
    "Uå": "Umeå C",
    "Uåö": "Umeå Östra",
    "Skc": "Skellefteå C",
    "Le": "Luleå C",
    "Bdn": "Boden C",
    "Gv": "Gällivare",
    "Kra": "Kiruna C",
    "Ab": "Abisko Östra",
}

# Lista över vanliga tågoperatörer i Sverige
OPERATOR_OPTIONS = [
    "alla",
    "Östgötapendeln",
    "SJ",
    "Mälartåg",
    "Västtågen",
    "Krösatågen",
    "Snälltåget",
    "SL",
    "Tåg i Bergslagen",
    "VR Snabbtåg",
    "Vy Tåg",
    "Öresundståg",
    "Tågab",
    "Inlandsbanan",
]

def _normalize_name(text: str) -> str:
    """Normaliserar text för flexibel stationssökning."""
    t = text.strip().lower()
    for src, dst in [("å", "a"), ("ä", "a"), ("ö", "o"), ("é", "e")]:
        t = t.replace(src, dst)
    return t.replace(" ", "").replace("-", "")

def _normalize_operator(s: str) -> str:
    """Normaliserar operatörssträng för jämförelse (tar bort accenter och bestämda ändelser)."""
    if not s:
        return ""
    t = s.lower().strip()
    for src, dst in [("å", "a"), ("ä", "a"), ("ö", "o"), ("é", "e")]:
        t = t.replace(src, dst)
    for suffix in ("en", "na", "n"):
        if t.endswith(suffix) and len(t) > len(suffix) + 3:
            t = t[:-len(suffix)]
            break
    return t.replace(" ", "").replace("-", "")

def resolve_station(user_input: str) -> tuple[str, str]:
    """Slår upp Trafikverkets signatur och visningsnamn från användarinmatning.
    
    Returnerar (signatur, visningsnamn). Om input är tomt eller 'alla' returneras ('', '').
    """
    if not user_input or user_input.strip().lower() in ("alla", "all", "*", "any", "-"):
        return "", ""

    q = user_input.strip()

    # 1. Direkt matchning på signatur
    for sig, name in STATIONS.items():
        if sig.lower() == q.lower():
            return sig, name

    # 2. Matchning mot stationsnamn
    norm_q = _normalize_name(q)
    for sig, name in STATIONS.items():
        if norm_q == _normalize_name(name):
            return sig, name

    for sig, name in STATIONS.items():
        if _normalize_name(name).startswith(norm_q):
            return sig, name

    for sig, name in STATIONS.items():
        if norm_q in _normalize_name(name):
            return sig, name

    # 3. Om inte i katalogen: använd inmatad sträng som signatur
    return q, q

def matches_operator(train: dict, operator_filter: str) -> bool:
    """Kontrollerar om ett tåg matchar önskad operatör/tågtyp."""
    if not operator_filter or operator_filter.strip().lower() in ("alla", "all", "*", "any", ""):
        return True

    filt = _normalize_operator(operator_filter)
    if not filt:
        return True

    # 1. Kontrollera Operator-fältet
    op_raw = str(train.get("Operator") or "")
    norm_op = _normalize_operator(op_raw)
    if norm_op:
        if filt == norm_op or filt in norm_op:
            return True
        if len(norm_op) >= 3 and norm_op in filt:
            return True

    # 2. Kontrollera ProductInformation (både Code och Description)
    prods = train.get("ProductInformation", [])
    if isinstance(prods, dict):
        prods = [prods]
    elif isinstance(prods, str):
        prods = [{"Description": prods}]
    elif not isinstance(prods, list):
        prods = []

    is_pendel_query = any(x in filt for x in ("ostgota", "pendel", "pnt", "jlt"))

    for p in prods:
        desc = p.get("Description", "") if isinstance(p, dict) else str(p)
        code = p.get("Code", "") if isinstance(p, dict) else ""
        norm_desc = _normalize_operator(desc)
        norm_code = _normalize_operator(code)

        if norm_desc and (filt in norm_desc or norm_desc in filt):
            return True
        if norm_code and (filt in norm_code or norm_code in filt):
            return True

        if is_pendel_query:
            if any(x in norm_desc for x in ("ostgota", "pendel")) or code.upper() in ("PNT", "JLT"):
                return True

    return False

def get_operator_display(train: dict) -> str:
    """Hämtar läsbar operatör eller tågprodukt för visning i tabellen."""
    prods = train.get("ProductInformation", [])
    if isinstance(prods, dict):
        prods = [prods]
    elif isinstance(prods, str):
        prods = [{"Description": prods}]
    elif not isinstance(prods, list):
        prods = []

    for p in prods:
        desc = p.get("Description", "") if isinstance(p, dict) else str(p)
        code = p.get("Code", "") if isinstance(p, dict) else ""
        if code in ("PNT", "JLT") or "östgötapendel" in desc.lower():
            return "Östgötapendeln"
        if desc:
            return desc

    op = train.get("Operator")
    if op:
        return str(op)

    return "Tåg"

def get_destination_display(train: dict) -> str:
    """Hämtar slutdestinationens namn för ett tåg."""
    to_loc = train.get("ToLocation", [])
    if isinstance(to_loc, dict):
        to_loc = [to_loc]
    elif isinstance(to_loc, str):
        to_loc = [{"LocationName": to_loc}]
    elif not isinstance(to_loc, list):
        to_loc = []

    dest_names = []
    for item in to_loc:
        sig = item.get("LocationName", "") if isinstance(item, dict) else str(item)
        if sig:
            dest_names.append(STATIONS.get(sig, sig))

    return ", ".join(dest_names) if dest_names else "-"

def fetch_departures(from_sig: str, to_sig: str = "", operator_filter: str = ""):
    """Hämtar tågavgångar för given station, destination och operatör via Trafikverkets API."""
    global last_error, total_trains_fetched

    to_filter_xml = ""
    if to_sig:
        to_filter_xml = f"""
                <OR>
                    <EQ name="ToLocation.LocationName" value="{to_sig}" />
                    <EQ name="ViaToLocation.LocationName" value="{to_sig}" />
                </OR>"""

    xml_query = f"""<REQUEST>
    <LOGIN authenticationkey="{API_KEY}" />
    <QUERY objecttype="TrainAnnouncement" schemaversion="1.4" orderby="AdvertisedTimeAtLocation">
        <FILTER>
            <AND>
                <EQ name="ActivityType" value="Avgang" />
                <EQ name="LocationSignature" value="{from_sig}" />{to_filter_xml}
                <GTE name="AdvertisedTimeAtLocation" value="$dateadd(-0:05:00)" />
                <LTE name="AdvertisedTimeAtLocation" value="$dateadd(02:00:00)" />
            </AND>
        </FILTER>
        <INCLUDE>AdvertisedTrainIdent</INCLUDE>
        <INCLUDE>AdvertisedTimeAtLocation</INCLUDE>
        <INCLUDE>EstimatedTimeAtLocation</INCLUDE>
        <INCLUDE>TrackAtLocation</INCLUDE>
        <INCLUDE>Canceled</INCLUDE>
        <INCLUDE>Deviation</INCLUDE>
        <INCLUDE>ProductInformation</INCLUDE>
        <INCLUDE>Operator</INCLUDE>
        <INCLUDE>ToLocation</INCLUDE>
    </QUERY>
</REQUEST>"""

    try:
        response = requests.post(
            API_URL, 
            data=xml_query.encode('utf-8'), 
            headers={'Content-Type': 'application/xml'},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        results = data.get('RESPONSE', {}).get('RESULT', [])
        if not results:
            last_error = "Tomt svar från Trafikverket"
            total_trains_fetched = 0
            return []
            
        first_result = results[0]
        if 'ERROR' in first_result:
            last_error = str(first_result['ERROR'])
            total_trains_fetched = 0
            return None

        trains = first_result.get('TrainAnnouncement', [])
        total_trains_fetched = len(trains)
        
        # Filtrera på operatör om angivet
        filtered = [t for t in trains if matches_operator(t, operator_filter)]
        last_error = ""
        return filtered

    except requests.exceptions.RequestException as e:
        last_error = f"Nätverksfel ({e.__class__.__name__})"
        total_trains_fetched = 0
        return None
    except Exception as e:
        last_error = str(e)
        total_trains_fetched = 0
        return None

def format_time(iso_str: str) -> str:
    """Omvandlar ISO-tidsstämpel till HH:MM."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%H:%M")
    except ValueError:
        return iso_str

def generate_layout(departures, last_updated: str, from_name: str, to_name: str = "", operator_filter: str = "", update_interval: int = 300):
    """Skapar en Layout som fyller hela terminalfönstret."""
    layout = Layout()

    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main", ratio=1),
        Layout(name="footer", size=3)
    )

    # Header Panel
    route_text = f"{from_name} ➡️ {to_name}" if to_name else f"Avgångar från {from_name}"
    op_badge = f"  |  Operatör: [bold cyan]{operator_filter}[/bold cyan]" if operator_filter and operator_filter.lower() not in ("alla", "all", "*") else "  |  Operatör: [bold cyan]Alla[/bold cyan]"
    layout["header"].update(
        Panel(
            Align.center(f"[bold white]🚆 TÅGSPÅR[/bold white]  •  [bold yellow]{route_text}[/bold yellow]{op_badge}"),
            style="bold white on blue"
        )
    )

    # Footer Panel
    mins = update_interval // 60
    interval_text = f"{mins} min" if mins > 0 else f"{update_interval} sek"
    layout["footer"].update(
        Panel(
            Align.center(f"[dim]Senast uppdaterad: [bold cyan]{last_updated}[/bold cyan]  |  Nästa uppdatering om {interval_text}  |  Tryck [bold red]Ctrl + C[/bold red] för att avsluta[/dim]"),
            style="white on black"
        )
    )

    # Tabell-byggande
    table_title = f"{from_name} ➡️ {to_name}" if to_name else f"Alla avgångar från {from_name}"
    table = Table(
        title=table_title,
        expand=True,
        border_style="bright_blue"
    )

    table.add_column("Tåg", style="cyan", justify="center", ratio=1)
    table.add_column("Destination", style="bold cyan", justify="left", ratio=3)
    table.add_column("Ordinarie tid", style="bold white", justify="center", ratio=2)
    table.add_column("Ny tid", style="bold yellow", justify="center", ratio=2)
    table.add_column("Spår", style="magenta", justify="center", ratio=1)
    table.add_column("Operatör", style="white", justify="center", ratio=3)
    table.add_column("Status / Avvikelser", style="green", ratio=4)

    if departures is None:
        err_msg = f"[bold red]Kunde inte hämta data ({last_error}).[/bold red]" if last_error else "[bold red]Kunde inte hämta data från Trafikverket.[/bold red]"
        table.add_row("-", "-", "-", "-", "-", "-", err_msg)
    elif not departures:
        if total_trains_fetched > 0 and operator_filter and operator_filter.lower() not in ("alla", "all", "*"):
            table.add_row("-", "-", "-", "-", "-", "-", f"[yellow]Inga avgångar för '{operator_filter}' ({total_trains_fetched} tåg med andra operatörer hittades).[/yellow]")
        else:
            table.add_row("-", "-", "-", "-", "-", "-", "[yellow]Inga avgångar hittades de närmsta 2 timmarna.[/yellow]")
    else:
        for train in departures:
            train_num = str(train.get("AdvertisedTrainIdent", "N/A"))
            dest_name = get_destination_display(train)
            sched_time = format_time(train.get("AdvertisedTimeAtLocation"))
            est_time = format_time(train.get("EstimatedTimeAtLocation"))
            track = str(train.get("TrackAtLocation", "-"))
            is_canceled = train.get("Canceled", False)
            op_name = get_operator_display(train)

            deviations_raw = train.get("Deviation", [])
            if isinstance(deviations_raw, dict):
                deviations_raw = [deviations_raw]
            elif isinstance(deviations_raw, str):
                deviations_raw = [{'Description': deviations_raw}]
            elif not isinstance(deviations_raw, list):
                deviations_raw = []

            deviations = []
            for d in deviations_raw:
                if isinstance(d, dict) and "Description" in d:
                    deviations.append(d["Description"])
                elif isinstance(d, str):
                    deviations.append(d)

            status_text = ", ".join(deviations) if deviations else "I tid"

            if is_canceled:
                status_text = "[bold red]INSTÄLLT[/bold red]"
                new_time_display = "-"
            elif est_time and est_time != sched_time:
                new_time_display = f"[bold red]{est_time}[/bold red]"
                status_text = f"[yellow]Försenat ({status_text})[/yellow]" if deviations else "[yellow]Försenat[/yellow]"
            else:
                new_time_display = "-"

            table.add_row(
                train_num,
                dest_name,
                sched_time,
                new_time_display,
                track,
                op_name,
                status_text
            )

    layout["main"].update(Panel(table, border_style="dim white"))
    return layout

def browse_stations(title: str = "Välj station", allow_all: bool = False) -> str:
    """Interaktiv stationsbläddrare med sökning och nummerval."""
    sorted_stations = sorted(STATIONS.items(), key=lambda x: x[1])

    while True:
        table = Table(title=f"🚆 {title}", border_style="bright_blue")
        table.add_column("#", style="bold yellow", justify="right")
        table.add_column("Station", style="bold white")
        table.add_column("Kod", style="cyan", justify="center")
        table.add_column("#", style="bold yellow", justify="right")
        table.add_column("Station", style="bold white")
        table.add_column("Kod", style="cyan", justify="center")

        half = (len(sorted_stations) + 1) // 2
        for i in range(half):
            s1 = sorted_stations[i]
            if i + half < len(sorted_stations):
                s2 = sorted_stations[i + half]
                table.add_row(str(i + 1), s1[1], s1[0], str(i + half + 1), s2[1], s2[0])
            else:
                table.add_row(str(i + 1), s1[1], s1[0], "", "", "")

        console.print(table)
        extra_note = "  |  Skriv '0' eller 'alla' för alla destinationer" if allow_all else ""
        console.print(f"[dim]Ange nummer (1-{len(sorted_stations)}), sökord (t.ex. 'göt', 'stock'), eller Tryck Enter för att avbryta{extra_note}:[/dim]")

        try:
            choice = input("👉 ").strip()
        except (EOFError, KeyboardInterrupt):
            return ""

        if not choice:
            return ""

        if allow_all and choice.lower() in ("0", "alla", "all", "*"):
            return "alla"

        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(sorted_stations):
                selected = sorted_stations[idx - 1]
                console.print(f"[green]Valde: [bold]{selected[1]}[/bold] ({selected[0]})[/green]\n")
                return selected[1]
            else:
                console.print(f"[red]Ogiltigt nummer. Välj mellan 1 och {len(sorted_stations)}.[/red]\n")
                continue

        # Sökning på text
        q = choice.lower()
        matches = [s for s in sorted_stations if q in s[1].lower() or q == s[0].lower()]
        if not matches:
            console.print(f"[yellow]Ingen station matchade '{choice}'. Försök igen.[/yellow]\n")
            continue
        elif len(matches) == 1:
            console.print(f"[green]Hittade: [bold]{matches[0][1]}[/bold] ({matches[0][0]})[/green]\n")
            return matches[0][1]
        else:
            # Flera träffar - visa resultat och låt användaren välja
            sub_table = Table(title=f"Resultat för '{choice}'", border_style="cyan")
            sub_table.add_column("#", style="bold yellow", justify="right")
            sub_table.add_column("Station", style="bold white")
            sub_table.add_column("Kod", style="cyan")
            for i, m in enumerate(matches, 1):
                sub_table.add_row(str(i), m[1], m[0])
            console.print(sub_table)

            try:
                sub_choice = input(f"Välj nummer (1-{len(matches)}) eller Enter för ny sökning: ").strip()
            except (EOFError, KeyboardInterrupt):
                return ""

            if sub_choice.isdigit():
                sub_idx = int(sub_choice)
                if 1 <= sub_idx <= len(matches):
                    return matches[sub_idx - 1][1]

def browse_operators() -> str:
    """Visar en lista över vanliga tågoperatörer och låter användaren välja."""
    table = Table(title="🚆 Kända tågoperatörer i Sverige", border_style="cyan")
    table.add_column("#", style="bold yellow", justify="right")
    table.add_column("Operatör", style="bold white")
    table.add_column("Beskrivning / Typ", style="dim cyan")

    op_descs = {
        "alla": "Alla tåg oavsett operatör",
        "Östgötapendeln": "Pendeltåg i Östergötland (Norrköping, Linköping, Mjölby, Tranås)",
        "SJ": "SJ Snabbtåg, InterCity, Regional och Nattåg",
        "Mälartåg": "Regionaltåg i Mälardalen (Stockholm, Uppsala, Linköping m.fl.)",
        "Västtågen": "Regional- och pendeltåg i Västra Götaland",
        "Krösatågen": "Regionaltåg i Småland och angränsande län",
        "Snälltåget": "Långdistanståg Stockholm-Malmö, Jämtland m.fl.",
        "SL": "SL Pendeltåg i Stockholms län",
        "Tåg i Bergslagen": "Regionaltåg i Bergslagen/Dalarna",
        "VR Snabbtåg": "Snabbtåg Göteborg-Stockholm",
        "Vy Tåg": "Nattåg till Norrland och Värmlandstrafik",
        "Öresundståg": "Öresundståg i södra Sverige och Danmark",
    }

    for i, op in enumerate(OPERATOR_OPTIONS, 1):
        desc = op_descs.get(op, "")
        table.add_row(str(i), op, desc)

    console.print(table)
    try:
        choice = input(f"Välj nummer (1-{len(OPERATOR_OPTIONS)}) eller skriv namn [Enter för att avbryta]: ").strip()
    except (EOFError, KeyboardInterrupt):
        return ""

    if not choice:
        return ""
    if choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(OPERATOR_OPTIONS):
            return OPERATOR_OPTIONS[idx - 1]
    return choice

def print_stations_list():
    """Skriver ut en lista över vanliga stationer och deras signaturer."""
    table = Table(title="🚆 Vanliga stationer i Tågspår", border_style="cyan")
    table.add_column("Signatur", style="bold yellow", justify="center")
    table.add_column("Stationsnamn", style="bold white")

    for sig, name in sorted(STATIONS.items(), key=lambda x: x[1]):
        table.add_row(sig, name)

    console.print(table)
    console.print("[dim]Du kan ange antingen stationsnamnet eller signaturen när du kör Tågspår.[/dim]\n")

def parse_arguments():
    """Hanterar kommandoradsargument."""
    parser = argparse.ArgumentParser(
        prog="Tågspår",
        description="🚆 Tågspår - Realtidsavgångar för tåg via Trafikverkets öppna API."
    )
    parser.add_argument(
        "-f", "--from",
        dest="from_station",
        default=os.environ.get("DEFAULT_FROM_STATION", "Nr"),
        help="Avgångsstation (namn eller signatur, t.ex. 'Nr', 'Norrköping', 'Cst', 'Stockholm'). Standard: Nr"
    )
    parser.add_argument(
        "-t", "--to",
        dest="to_station",
        default=os.environ.get("DEFAULT_TO_STATION", "Lp"),
        help="Destination (namn eller signatur, eller 'alla' för alla destinationer). Standard: Lp"
    )
    parser.add_argument(
        "-o", "--operator",
        dest="operator",
        default=os.environ.get("DEFAULT_OPERATOR", "alla"),
        help="Operatör/tågtyp att filtrera på (t.ex. 'Östgötapendeln', 'SJ', 'Mälartåg', eller 'alla'). Standard: alla"
    )
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Starta med interaktiv inmatning av stationer och operatör"
    )
    parser.add_argument(
        "-b", "--browse",
        action="store_true",
        help="Öppna den interaktiva stationsbläddraren vid start"
    )
    parser.add_argument(
        "-d", "--default",
        action="store_true",
        help="Kör direkt med standardvärden utan interaktiva frågor"
    )
    parser.add_argument(
        "--list-stations",
        action="store_true",
        help="Visa lista över vanliga stationer och avsluta"
    )
    parser.add_argument(
        "-u", "--update-interval",
        type=int,
        default=int(os.environ.get("UPDATE_INTERVAL_SECONDS", str(DEFAULT_UPDATE_INTERVAL))),
        help="Uppdateringsintervall i sekunder (standard: 300)"
    )
    return parser.parse_args()

def main():
    """Huvudfunktion som startar Tågspår."""
    args = parse_arguments()

    if args.list_stations:
        print_stations_list()
        sys.exit(0)

    if not API_KEY:
        console.print(
            Panel(
                "[bold red]Fel: Ingen API-nyckel hittades![/bold red]\n\n"
                "Sätt [bold cyan]TRAFIKVERKET_API_KEY[/bold cyan] i din [cyan].env[/cyan]-fil eller som miljövariabel.\n"
                "Exempel i [cyan].env[/cyan]:\n"
                "  [green]TRAFIKVERKET_API_KEY=din_api_nyckel[/green]\n\n"
                "Se [cyan].env.example[/cyan] för referens.",
                title="Konfigurationsfel",
                border_style="red"
            )
        )
        sys.exit(1)

    from_input = args.from_station
    to_input = args.to_station
    op_input = args.operator

    # Interaktiv fråga om flaggan -i / -b angavs, ELLER om användaren kör interaktivt i terminalen utan stationsflaggor
    has_cli_station_flags = any(arg in sys.argv for arg in ("-f", "--from", "-t", "--to", "-o", "--operator"))
    is_interactive_mode = args.interactive or args.browse or (not args.default and not has_cli_station_flags and sys.stdin.isatty())

    if is_interactive_mode:
        console.print(
            Panel(
                Align.center(
                    "[bold white]🚆 TÅGSPÅR - REALTIDSAVGÅNGAR[/bold white]\n"
                    "[dim]Tryck [bold cyan]<Tab>[/bold cyan] för att autokomplettera, eller skriv [bold yellow]?[/bold yellow] för att bläddra.[/dim]"
                ),
                border_style="bright_blue"
            )
        )

        # 1. Välj avgångsstation
        station_completions = sorted(list(STATIONS.values()) + list(STATIONS.keys()))
        set_tab_completer(station_completions)

        if args.browse:
            chosen = browse_stations(title="Välj avgångsstation")
            if chosen:
                from_input = chosen
        else:
            while True:
                set_tab_completer(station_completions)
                inp = Prompt.ask("Avgångsstation [dim](eller '?' för att bläddra)[/dim]", default=from_input)
                if inp.strip() in ("?", "b", "bläddra", "browse"):
                    chosen = browse_stations(title="Välj avgångsstation")
                    if chosen:
                        from_input = chosen
                        break
                else:
                    from_input = inp
                    break

        # 2. Välj destination
        dest_completions = station_completions + ["alla"]
        set_tab_completer(dest_completions)

        if args.browse:
            chosen = browse_stations(title="Välj destination", allow_all=True)
            if chosen:
                to_input = chosen
        else:
            while True:
                set_tab_completer(dest_completions)
                inp = Prompt.ask("Destination [dim](eller '?' för att bläddra, 'alla' för alla)[/dim]", default=to_input)
                if inp.strip() in ("?", "b", "bläddra", "browse"):
                    chosen = browse_stations(title="Välj destination", allow_all=True)
                    if chosen:
                        to_input = chosen
                        break
                else:
                    to_input = inp
                    break

        # 3. Välj operatör
        set_tab_completer(OPERATOR_OPTIONS)
        while True:
            set_tab_completer(OPERATOR_OPTIONS)
            inp = Prompt.ask("Operatör [dim](eller '?' för lista, 'alla' för alla)[/dim]", default=op_input)
            if inp.strip() in ("?", "b", "lista", "bläddra", "browse"):
                chosen = browse_operators()
                if chosen:
                    op_input = chosen
                    break
            else:
                op_input = inp
                break

    from_sig, from_name = resolve_station(from_input)
    to_sig, to_name = resolve_station(to_input)
    operator_filter = "" if op_input.strip().lower() in ("alla", "all", "*") else op_input.strip()

    if not from_sig:
        console.print("[bold red]Fel: Du måste ange en giltig avgångsstation.[/bold red]")
        sys.exit(1)

    update_interval = max(5, args.update_interval)

    # Full-screen Live loop
    with Live(console=console, screen=True, refresh_per_second=1) as live:
        while True:
            last_updated = datetime.now().strftime("%H:%M:%S")
            departures = fetch_departures(from_sig, to_sig, operator_filter)

            layout = generate_layout(
                departures=departures,
                last_updated=last_updated,
                from_name=from_name,
                to_name=to_name,
                operator_filter=operator_filter,
                update_interval=update_interval
            )
            live.update(layout)

            # Sov i korta intervaller för responsiv Ctrl + C
            for _ in range(update_interval // 2):
                time.sleep(2)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Tågspår avslutades.[/bold yellow]")
        sys.exit(0)