# Tågspår 🚆

Ett flexibelt terminalbaserat verktyg (TUI) byggt i Python med `rich` som visar realtidsavgångar, spårinformation, förseningar och avvikelser för tåg i Sverige via Trafikverkets öppna API.

Du kan välja valfria avgångs- och ankomststationer i hela landet samt filtrera på specifika tågoperatörer (eller se alla avgångar).

---

## Funktioner

- ⚡ **Tab-komplettering**: Tryck `<Tab>` för att autokomplettera operatörer (t.ex. `Öst<Tab>` ➡️ `Östgötapendeln`, `S<Tab>` ➡️ `SJ`, `Mäl<Tab>` ➡️ `Mälartåg`) och stationsnamn (t.ex. `Norr<Tab>` ➡️ `Norrköping C`).
- 🗺️ **Stationsbläddrare**: Skriv `?` eller starta med `-b`/`--browse` för att bläddra bland över 50 svenska stationer med snabbval via nummer och sökning.
- 🏢 **Operatörsbläddrare**: Skriv `?` vid operatörsvalet för att se en lista över kända svenska operatörer med beskrivningar.
- ⏱️ **Fullskärms realtidsvy**: Visar tågnummer, destination, ordinarie och ny tid, spår, operatör och avvikelser med automatisk uppdatering.

---

## Installation

1. Klona projektet och navigera till mappen:
   ```bash
   cd t-gsp-r-app
   ```

2. Aktivera den virtuella miljön:
   ```bash
   source .venv/bin/activate
   ```

3. Installera beroenden:
   ```bash
   pip install -r requirements.txt
   ```

---

## Konfiguration

Skapa en `.env`-fil i projektets rotmapp (se `.env.example`):

```env
TRAFIKVERKET_API_KEY=din_api_nyckel_har
```

Du kan hämta en gratis API-nyckel på [Trafikverkets API-portal](https://data.trafikverket.se/).

Valfria förval i `.env`:
```env
DEFAULT_FROM_STATION=Nr
DEFAULT_TO_STATION=Lp
DEFAULT_OPERATOR=alla
UPDATE_INTERVAL_SECONDS=300
```

---

## Användning

### 1. Interaktivt läge med Tab-komplettering & Bläddring

Starta programmet direkt:

```bash
python scr/app.py
```

- **Autokomplettera**: Tryck `<Tab>` när som helst för att komplettera stationer eller operatörer.
- **Bläddra bland stationer**: Skriv `?` i stationsfrågan för att öppna den interaktiva stationsbläddraren och välja via nummer eller sökord.
- **Lista operatörer**: Skriv `?` i operatörsfrågan för att lista kända tågoperatörer.
- **Behåll förvalt värde**: Tryck `Enter`.

### 2. Öppna stationsbläddraren direkt

```bash
python scr/app.py --browse
# eller kortform:
python scr/app.py -b
```

### 3. Med kommandoradsflaggor

Du kan ange stationer antingen med namn (t.ex. `Stockholm`, `Norrköping`, `Göteborg`) eller med Trafikverkets signatur (t.ex. `Cst`, `Nr`, `G`):

```bash
# Se tåg mellan Stockholm C och Göteborg C med SJ
python scr/app.py --from Stockholm --to Göteborg --operator SJ

# Se alla avgångar från Uppsala C (oavsett destination och operatör)
python scr/app.py -f Uppsala -t alla -o alla

# Östgötapendeln mellan Norrköping och Linköping
python scr/app.py -f Nr -t Lp -o Östgötapendeln

# Starta direkt med standardvärden utan frågor
python scr/app.py -d
```

### 4. Lista vanliga stationer och signaturer

```bash
python scr/app.py --list-stations
```

### 5. Alla flaggor

```
options:
  -h, --help            visa hjälpmeddelande och avsluta
  -f, --from            Avgångsstation (namn eller signatur, t.ex. 'Nr', 'Stockholm'). Standard: Nr
  -t, --to              Destination (eller 'alla' för alla destinationer). Standard: Lp
  -o, --operator        Operatör att filtrera på (t.ex. 'Östgötapendeln', 'SJ', 'Mälartåg', eller 'alla'). Standard: alla
  -i, --interactive     Starta med interaktiva frågor
  -b, --browse          Öppna den interaktiva stationsbläddraren vid start
  -d, --default         Starta direkt med standardvärden utan frågor
  --list-stations       Visa lista över vanliga stationer och avsluta
  -u, --update-interval Uppdateringsintervall i sekunder (standard: 300)
```

Tryck `Ctrl + C` för att avsluta programmet.
