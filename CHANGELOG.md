# Changelog

All notable changes to the PC User Statistics Home Assistant integration will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---
## [Backend] __init__.py 2.16.0 - 2026-08-22

### Changed

- **Monthly og daily totals-bogføring samlet i én `PeriodTracker`-klasse** (ny fil `period_tracker.py`, bruges fra `__init__.py`):
  - **Baggrund**: `self.monthly`/`self._pending` og `self.daily`/`self._daily_pending` var to hånd-duplikerede implementeringer af samme logik (totals, pending-buffer før InfluxDB-load, baseline-floor-merge, rollover-reset). Daily-trackeren (v2.15.0) opstod netop som en bugfix for at denne duplikering havde fået "i dag"-sammenligningen til fejlagtigt at bruge månedstotalen.
  - **Ændring**: `PeriodTracker(period, tracked_users)` indkapsler nu bogføringen rent (ingen I/O — InfluxDB-kald og NotificationStore bliver i coordinatoren). `self._monthly_tracker` og `self._daily_tracker` erstatter de gamle attributter internt.
  - **Ingen adfærdsændring**: `self.monthly`, `self.daily`, `self._monthly_loaded`, `self._daily_loaded` findes stadig — nu som properties der delegerer til trackerne — så `websocket.py`, `sensor.py`, `diagnostics.py` og `system_health.py` er uændrede.
  - **Tests**: Ny `tests/test_period_tracker.py` (23 isolerede tests, ingen HA-mocking påkrævet). `tests/test_init.py::TestGetData` opdateret til at bygge rigtige `PeriodTracker`-instanser i stedet for at sætte `coordinator.monthly`/`._pending` direkte, plus nye tests for daily-view og monthly/daily-uafhængighed.


---
## [Frontend] pc-user-statistics-cards.js 2.6.12 - 2026-08-21

### Fixed

- **Mobilvisning af `pc-user-statistics-tablet-card` var brudt — elementer overlappede/klippede hinanden** (`frontend/pc-user-statistics-cards.js`):
  - **Problem**: Kortet kunne oprindeligt tilpasse sig både tablet og mobil, men de tabletfokuserede rettelser i 2.6.x-serien (fast `7fr 3fr`-grid, `_updateScale()` der udelukkende skalerede efter `window.innerHeight`) ødelagde mobil-visningen. En telefon i portræt har en `innerHeight` tæt på tablettens, så den fik næsten samme skrift-/afstandsopskalering — bare i en højre-kolonne 4–5× smallere, hvilket klippede brugernavne, legend-tekst ("Flemming" → "Flemmin") og gauge-labels ("GPU TEMP", "SPEED").
  - **Fix**: `_updateScale()` bruger nu den **mindste** af en højde-baseret og en målt-bredde-baseret skalering, og sætter en `is-mobile`-klasse på host-elementet under 700px målt bredde. CSS skifter `.main-row` fra `7fr 3fr`-grid til én stablet kolonne under den klasse (bruger-kort øverst, donut/live/gauges under), og formindsker donut-ring + gauge-højde til mobil-format. `.legend-name` fik en ellipsis-fallback som ekstra sikkerhedsnet. Tablet-visningen (≥700px) er upåvirket.


---
## [Frontend] pc-user-statistics-cards.js 2.6.11 - 2026-08-08

### Fixed

- **Donut blev stadig ikke større, selv efter fuld sidegenindlæsning på tabletten** (`frontend/pc-user-statistics-cards.js`):
  - **Problem**: Den JS-målte størrelse fra 2.6.9 (`_sizeDonut()`, baseret på `.right-col`'s målte bredde) endte fortsat på den lille 180px CSS-fallback, også efter en reelt bekræftet frisk side-indlæsning (cache udelukket som årsag).
  - **Fix**: JS-målingen er fjernet helt. `.donut-ring` bruger nu det klassiske "padding-bottom procent"-trick (`width:92%; height:0; padding-bottom:92%`) — en teknik der har været pålidelig i alle browsere siden CSS2.1, uden `aspect-ratio`, uden `calc()`-enheds-division, og uden JS der kan fejle stille.


---
## [Frontend] pc-user-statistics-cards.js 2.6.10 - 2026-08-08

### Fixed

- **Donut blev for lille efter 2.6.9-omskrivningen** (`frontend/pc-user-statistics-cards.js`): `_sizeDonut()`'s loft på 340px var langt under hvad den faktiske ~570px brede højre kolonne på tabletten har plads til. Loft hævet til 460px og andelen af kolonnens bredde brugt fra 0,9 til 0,98.


---
## [Frontend] pc-user-statistics-cards.js 2.6.9 - 2026-08-08

### Fixed

- **Donut fulgte stadig ikke toppen af venstre kolonne, trods 2.6.8-forsøget** (`frontend/pc-user-statistics-cards.js`):
  - **Problem**: `justify-content: flex-start` + `aspect-ratio: 1` på `.donut-ring` opførte sig ikke pålideligt i tablettens WebView — samme type kvirk som `calc(vh/px)`-fejlen fra v2.6.5.
  - **Fix**: Donuttens størrelse sættes nu direkte i JavaScript (`_sizeDonut()`, målt ud fra `.right-col`'s faktiske bredde, begrænset 120–340px) lige efter hvert render og ved vindues-resize. `.donut-wrap` er nu en almindelig `flex-shrink:0`-blok øverst i højre kolonne — ingen CSS-vokse/centrerings-tricks nødvendige.

### Changed

- **Større, tydeligere donut-legend** (Flemming/Lukas/Sebastian-listen under donutten): skrift 13px → 19px + halvfed, prikker 8px → 14px, mere række-afstand, federe procent-tekst.


---
## [Frontend] pc-user-statistics-cards.js 2.6.8 - 2026-08-08

### Changed

- **Donut-justering og større tekst i venstre kolonne** (`frontend/pc-user-statistics-cards.js`):
  - Donuttens top flugter nu med toppen af Flemmings kort i stedet for at være lodret centreret i højre kolonne (`.donut-wrap` skiftet fra `justify-content: center` til `flex-start`). Ringen er også en anelse mindre (`max-width` 100% → 88%).
  - Tekststørrelser i Flemming/Lukas/Sebastian-kortene hævet for bedre læsbarhed på afstand: brugernavn 13px → 20px, Tid/Energi/Pris/Skærm-rækker 12px → 17px (og federe værdi-tekst), lille avatar 28px → 40px.


---
## [Frontend] pc-user-statistics-cards.js 2.6.7 - 2026-08-08

### Changed

- **Donut i højre kolonne var stadig en lille fast cirkel efter 2.6.6-redesignet** (`frontend/pc-user-statistics-cards.js`):
  - **Problem**: Højre kolonne så tom/ubalanceret ud ved siden af den nu fuld-højde venstre kolonne — donutten fyldte stadig kun ~120px.
  - **Fix**: `.donut-wrap` er nu `flex: 1` og opsluger al resterende lodret plads i `.right-col` (live-status/gauges nedenunder beholder deres naturlige kompakte størrelse). `.donut-ring` sizes udelukkende via `aspect-ratio: 1` ud fra sin egen udregnede flex-højde (begrænset af `max-width: 100%`), og selve SVG'en fylder den boks 100%. Ingen magiske pixel-tal — en responsiv firkant der vokser/krymper efter tilgængelig plads. Center-tekst (%/navn) og legend-rækkernes skriftstørrelser er hævet til at matche den nu meget større ring.


---
## [Frontend] pc-user-statistics-cards.js 2.6.6 - 2026-08-08

### Changed

- **Layout omlagt for at fylde pladsen fuldt ud på tabletten** (`frontend/pc-user-statistics-cards.js`):
  - `.main-row` er nu CSS Grid med `grid-template-columns: 7fr 3fr` (70/30-split ml. bruger-kort og donut/gauges), som automatisk tilpasser sig uanset skærmstørrelse — erstatter den gamle faste-bredde højre-kolonne.
  - `.user-card` bruger nu `flex: 1`, så de 3 månedlige brugerkort deler den fulde tilgængelige højde i venstre kolonne ligeligt.
  - Ny `.user-stats`-wrapper med `justify-content: space-evenly` så Tid/Energi/Pris/Skærm-rækkerne breder sig ud i det højere kort i stedet for at klumpe sig sammen foroven.
  - `.right-col` bruger samme `space-evenly`-fordeling for donut/live-session/gauges.


---
## [Frontend] pc-user-statistics-cards.js 2.6.5 - 2026-08-08

### Fixed

- **Højde-skalering på tabletten virkede slet ikke, kun bredden** (`frontend/pc-user-statistics-cards.js`):
  - **Problem**: `--sm-scale-h: clamp(0.8, calc(100vh / 800px), 1.8)` (v2.6.3) deler en `vh`-enhed med en `px`-enhed inde i `calc()`. Det er ikke pålideligt understøttet på tværs af WebViews — på tablettens kiosk-browser faldt custom property'en stille tilbage til sin standardværdi, så alle `calc(Npx * var(--sm-scale-h))`-størrelser forblev ved deres 7"-tablet-bæreværdier. Bredden virkede fordi den er ren flex/procent-baseret og ikke afhænger af denne variabel.
  - **Fix**: Skaleringsfaktoren beregnes nu i JavaScript (`_updateScale()`, baseret på `window.innerHeight`) og sættes som inline custom property på kort-elementet via `style.setProperty()`. Køres ved `connectedCallback`/`setConfig` og holdes opdateret via en `resize`-listener. CSS-fallback'en er nu blot `--sm-scale-h: 1`.


---
## [Frontend] pc-user-statistics-cards.js 2.6.4 - 2026-08-08

### Fixed

- **Højre kolonne (donut/gauges) skubbede venstre kolonne smallere på tabletten** (`frontend/pc-user-statistics-cards.js`):
  - **Problem**: v2.6.3's `--sm-scale-h` skalerede `.donut-svg` og avatarer op i både bredde og højde (for at forblive runde), men `.right-col` beholdt en fast `width: 150px`. Ved skala 1.5x blev donut'en 180px bred i en 150px kolonne, som derfor visuelt voksede sig bredere og pressede `.left-col` smallere.
  - **Fix**: `.right-col` bruger nu også `calc(150px * var(--sm-scale-h))`.


---
## [Frontend] pc-user-statistics-cards.js 2.6.3 - 2026-08-08

### Fixed

- **`pc-user-statistics-tablet-card` skalerede ikke til den nye 11" tablet** (`frontend/pc-user-statistics-cards.js`):
  - **Problem**: Kortet var tunet til den gamle 7" Lenovo-tablet (1280x800) og efterlod tomrum i bunden på den nye Samsung Tab A11+ (1920x1200, samme 16:10-format).
  - **Fix**: Tilføjet `--sm-scale-h: clamp(0.8, calc(100vh / 800px), 1.8)` på `:host`, samme mønster som `secure_me_alarm_tab_card.js`. Alle lodrette paddings/gaps/font-størrelser/element-højder (`.card`, `.user-card`, `.donut-svg`, `.live-block`, `.gauge-bars`, `.avatar` m.fl.) er wrappet i `calc(Npx * var(--sm-scale-h))`. Kun højde ændret — bredde/kolonne-layout er urørt.


---
## [2.15.0] - 2026-07-17

### Fixed

- **Statistik-tabbens MS Family Safety-sammenligning sammenlignede forkerte tidsvinduer** (`__init__.py`, `store.py`, `const.py`, `websocket.py`, `pc-user-statistics-panel.js`):
  - **Problem**: "Skærmtid i dag"-widgeten sammenlignede Microsoft Family Safetys skærmtid *i dag* mod PC'ens *hele måneds*-total (`this._stats.monthly`) — begge labelet "i dag". Jo længere måneden skår frem, jo mere misvisende blev sammenligningen.
  - **Fix**: Ny `self.daily`-tracker i coordinatoren, en fuldstændig sideordnet parallel til `self.monthly` — samme delta-akkumulering, samme InfluxDB-indlæsning med baseline-floor-beskyttelse (`_persisted_daily_baseline`), samme periodiske persistering og samme robusthed mod restart/reload-datatab som månedstrackeren fik i v2.14.0. Nulstilles ved lokal midnat i stedet for månedsskift. `panel.js` bruger nu `daily` i stedet for `monthly` til MS-sammenligningen.
  - Ny `ws_get_stats`-felt: `daily` + `daily_loaded`.

- **Måneds- og dags-skifte brugte UTC i stedet for lokal tid** (`__init__.py`, ny `LOCAL_TIMEZONE`-konstant i `const.py`):
  - Samme klasse fejl som Historik-tabbens tz-fix (v3.5.0): UTC-døgnskifte falder kl. 02:00 dansk sommertid, ikke ved midnat — så måneds-/dags-rollover i coordinatoren kunne udløses op til 2 timer for sent.
  - **Fix**: Måneds- og dags-skifte tjekkes nu via `Europe/Copenhagen`-lokaltid (`zoneinfo.ZoneInfo`). InfluxDB-forespørgslernes start-tidspunkt (både måned og dag) beregnes nu fra lokal midnat, konverteret til UTC, i stedet for UTC-midnat direkte.


## [2.14.0] - 2026-07-17

### Fixed

- **Kritisk: månedlige totaler kunne stille falde ved genstart/reload** (`__init__.py`, `store.py`, `const.py`):
  - **Problem**: `_async_load_monthly_data()` overskrev `self.monthly` ubetinget med InfluxDB's SUM-forespørgsel — ved **enhver** coordinator-genstart (HA-genstart, eller integration-reload udløst af enhver konfigurations-gem). Hvis InfluxDB manglede nyligt skrevne punkter på det præcise tidspunkt (fx fordi de sad fast i den RAM-only `failed_writes`-bufferen under et udfald), blev den friske sum lavere end det der allerede var vist — og slettede dermed reel, allerede-talt spilletid/energi/pris stille fra visningen.
  - **Bekræftet i produktion**: recorder's egen historik for `sensor.statistics_sebastian_duration` viste månedstallet falde midt i måneden (uden månedsskift) mindst 4 gange i juli. Sammenholdt med Microsoft Family Safety som uafhængigt facit viste det sig at **~43,5 timers spilletid for Sebastian alene i én uge** var forsvundet fra InfluxDB/panelet.
  - **Fix**: Ny månedlig baseline (`self._persisted_monthly_baseline`) persisteres til config-storen (`store.py` — `get_monthly_baseline()`, `save_monthly_baseline_in_memory()`, `async_flush_monthly_baseline()`) hvert 60. sekund, efter hver vellykket InfluxDB-indlæsning, og ved shutdown. `_async_load_monthly_data()` tager nu `max(InfluxDB-sum, baseline)` per bruger/metrik — kan kun gå op, aldrig ned — og falder tilbage til baseline i stedet for at nulstille til 0, hvis alle 3 InfluxDB-forsøg fejler. Baseline nulstilles korrekt ved ægte månedsskift.
  - `_async_load_monthly_data()` planlægges nu eksplicit fra `async_setup_entry` (efter `_store`/baseline er koblet på) i stedet for i `__init__` — fjerner et kapløb hvor den første indlæsning kunne køre før baseline var tilgængelig.

- **`MAX_RETRY_ATTEMPTS` hævet 3 → 20** (`const.py`): fejlede InfluxDB-writes blev tidligere droppet permanent efter kun 3 forsøg — længe før det egentlige 100-punkts FIFO-loft nogensinde blev relevant. FIFO-loftet er nu den reelle grænse.

- **Timezone-fix i Historik-forespørgslen** (`websocket.py` — `_query_history`): `GROUP BY time(1d)` brugte InfluxDB's UTC-standard i stedet for `Europe/Copenhagen`. Med sommertid (UTC+2) lå døgnskiftet kl. 02:00 lokal tid — sessioner mellem midnat og kl. 02 blev talt på den forkerte dag i Historik-tabben. Rettet med `tz('Europe/Copenhagen')`.

### Data-korrektion

- **Sebastians juli-data genskabt** via "Manuel korrektion" (`source=manual` InfluxDB-punkter) for 11.-16. juli, baseret på Microsoft Family Safety (enheds-specifikt for FLEMMING_GAMER) som uafhængigt facit for tid, og faktiske historiske spotpriser fra `sensor.energy_hub_elhub_price_total` (via recorder) for prisestimatet. Energi estimeret ud fra observeret gennemsnitsforbrug (~0,16 kW), da de oprindelige watt-målinger for de tabte perioder aldrig nåede InfluxDB. I alt genskabt: 2608 min (43t28m), 6,955 kWh, 12,42 kr.


## [2.13.0] - 2026-07-17

### Added

- **Bedre forbrugsvisning — kr/time og kr/kWh** (`pc-user-statistics-panel.js` 3.2.0 → 3.5.0):
  - **Live-tab**: nyt 4. stat-kort "Kr/time lige nu" — beregnes client-side som `(watt/1000) × pris_entity`, læst direkte fra HA state ligesom `watt_entity`. Vises kun når både watt og pris er tilgængelige.
  - **Statistik-tab**: hvert brugerkort får nu en 4. linje "Gns. kr/time" (`cost / (time/3600)`), så man kan se om nogen "spiller dyrt" ift. bare meget spilletid.
  - **Historik-tab**: ny 4. metric "Kr/kWh" i metric-selectoren ud over Tid/Energi/Pris. Viser om en dyr dag skyldes mere spilletid eller dyrere strøm. Måneds- og ugetotaler for denne metric bruger et vægtet gennemsnit (`sum(cost)/sum(energy)`) i stedet for en naiv sum af daglige rater, så tallet er matematisk korrekt.

- **Robust prisfallback — luk hul der kunne give stille 0-kroner-perioder** (`const.py`, `__init__.py`, `store.py`, `websocket.py`, `pc-user-statistics-panel.js` 3.6.0):
  - **Problem**: `_get_price()` returnerede tidligere `0.0` DKK/kWh når prissensoren (`price_entity`) var `unavailable`/`unknown`/uparsbar — tid og energi blev stadig talt korrekt, men den periodes omkostning forsvandt helt, uden log eller synlighed.
  - **Fix**: `_get_price()` cacher nu seneste kendte gyldige pris og falder tilbage til den i stedet for 0.0. Kun 0.0 hvis der aldrig er set en gyldig pris (f.eks. lige efter HA-opstart).
  - Fallback-brug tælles (`_price_fallback_count`, nulstilles ved månedsskift) og logges som en rate-limited advarsel (højst hvert 5. minut via ny `PRICE_FALLBACK_LOG_INTERVAL`-konstant), så et sensor-udfald er synligt i loggen i stedet for stille.
  - Prisfallback-cachen (`last_valid_price` + `last_valid_price_time`) gemmes nu også i sessionssnapshottet (`store.py` `save_session_in_memory()`), så den overlever en HA-genstart — kasseres dog hvis den er ældre end 6 timer.
  - Ny helper `_is_price_entity_ok()` på coordinatoren, brugt af `ws_get_health` til at eksponere `price_fallback_count`, `last_valid_price` og `price_entity_ok`.
  - Ny "Prissensor"-health-metric på Admin-tabben: grøn ✅ ("OK"), gul ⚠️ ("OK (X× fallback denne måned)") eller rød ❌ ("Fallback (X,XX kr/kWh)") alt efter status.
  - Fundet og løst som led i en sammenligning med `server_monitor`-integrationens omkostningsberegning (som bruger en fast gennemsnitspris i stedet for live spotpris — se commit-diskussion for baggrund).


## [2.11.0] - 2026-06-13

### Added

- **Manuel korrektion til sjældne data-tab** (`__init__.py`, `websocket.py`, `pc-user-statistics-panel.js`):
  - Ny coordinator-metode `async_add_manual_entry()` skriver et ekstra `pc_usage`-punkt til InfluxDB tagget `source=manual`, og genindlæser månedstotalerne med det samme
  - Ny WS-kommando `pc_user_statistics/add_manual_entry` (15. kommando) — validerer bruger, dato (YYYY-MM-DD) og tid (minutter); energi (kWh) og pris (DKK) er valgfri
  - Ny sektion "Manuel korrektion" på Admin-tab: formular til bruger, dato, tid, energi og pris, med succes-/fejl-banner
  - Brugscase: en session der ikke blev registreret automatisk (f.eks. filer overskrevet midt i en session) kan nu rettes direkte i panelet i stedet for manuel InfluxDB line-protocol write


## [2.10.0] - 2026-06-13

### Fixed

- **`websocket.py` — `_get_coordinator()` brugte skrøbelig duck-typing** (Fix 1):
  - Iterede tidligere over `hass.data[DOMAIN].values()` og tjekkede `hasattr(value, "tracked_users")` for at finde coordinator'en
  - Nu sættes `entry.runtime_data = coordinator` i `async_setup_entry` (`__init__.py`), og `_get_coordinator()` slår op via `hass.config_entries.async_entries(DOMAIN)` — moderne HA-mønster, robust mod ekstra nøgler i `hass.data[DOMAIN]`

- **`__init__.py` — `user_map` kunne stadig indeholde dict-værdier efter normalisering** (Fix 4):
  - `_normalize_user_map()` normaliserer allerede til plain strings, men der var ingen kontrol af om det reelt skete
  - Ny defensiv assertion i `__init__`: ikke-string værdier logges som fejl og fjernes fra `user_map`, så `_handle_user_change()` ikke længere skal håndtere dicts on-the-fly

### Added

- **`__init__.py` — Livsguard for periodisk session-flush** (Fix 2):
  - `_schedule_session_flush()` logger nu en advarsel hvis forrige flush er >90s forsinket mens en session er aktiv — gør en "stille død" flush-timer synlig i loggen
  - Ny `_last_flush_monotonic`-tracking (monotonic clock, robust mod systemur-ændringer)

- **`websocket.py` — `ws_get_health` eksponerer flush-timer status** (Fix 3):
  - Nye felter `flush_timer_active` og `flush_interval_s` i svaret
  - Giver Admin-tab mulighed for at vise grøn/rød indikator for "periodisk backup aktiv"


## [2.7.0] - 2026-03-14

### Added

- **Session persistence — overlever HA-genstart midt i en session** (`store.py`, `__init__.py`):
  - Session-state (`current_user`, `acc_time`, `acc_energy`, `acc_cost`, `last_time`) gemmes nu til disk ved hvert succesfuldt InfluxDB-write (~hvert 60s)
  - Ved HA-startup gendannes sessionen automatisk — ingen tid, energi eller pris går tabt
  - Maksimalt tab ved HA-genstart: ~60s (svarer til ét poll-interval)
  - Ingen ekstra disk-writes: session piggybacks på den eksisterende notification-flush
  - Sikkerheds-tjek ved genoprettelse:
    - Snapshot afvises hvis det er ældre end 4 timer (PC var slukket)
    - Snapshot afvises hvis den gemte bruger ikke længere er i `tracked_users`
    - Snapshot afvises hvis en anden bruger allerede er aktiv på sensoren
  - Session ryddes fra disk ved ren logout — ingen ghost-sessions ved næste opstart
  - Nye metoder i `store.py`: `get_session()`, `save_session_in_memory()`, `async_flush_session()`, `async_clear_session()`
  - Ny metode i `__init__.py`: `_async_restore_session()`


## [2.6.2] - 2026-03-08

### Fixed

- **`__init__.py` — Månedlig data loader aldrig fra InfluxDB** (`_async_load_monthly_data`):
  - `datetime.isoformat()` returnerede `2026-03-01T00:00:00+00:00` i WHERE-klausulen
  - InfluxDB 1.x accepterer ikke `+00:00` — kræver `Z`-suffix (RFC3339)
  - Query returnerede tom serie, `_monthly_loaded` forblev `False` permanent
  - System Health viste "Afventer InfluxDB..." og panelet viste spinner for altid
  - **Fix**: Ændret til `.strftime("%Y-%m-%dT%H:%M:%SZ")` — samme mønster som `_query_history()` i `websocket.py` allerede brugte korrekt

- **`__init__.py` — `last_write_time` initialiseret forkert** (`__init__`):
  - `self.last_write_time = time.time()` ved startup gav en falsk "aldrig"-visning
  - System Health viste orange "aldrig" selv under normal drift uden aktiv bruger
  - **Fix**: Initialiseret til `0.0` — nul betyder eksplicit "ingen write endnu"

- **`system_health.py` — System Health viste vildledende statusser**:
  - `monthly_data_loaded` returnerede rå boolean → HA viste ✅/❌ for en forbigående loading-tilstand
  - `last_influxdb_write` viste orange "aldrig" selvom PC blot var idle (ingen aktiv session)
  - **Fix**: `monthly_data_loaded` returnerer nu tekst ("Indlæst ✓" / "Afventer InfluxDB...")
  - **Fix**: `last_influxdb_write` skelner nu mellem "ingen aktiv session" (neutral) og "aldrig" (kun når bruger er aktiv men ingen write er sket)

### Changed

- **`pc-user-statistics-panel.js` — Tab-struktur omstruktureret**:
  - `statistik`-tab (tidligere `statistics`) omdøbt til **`live`** 🎮 — viser udelukkende live session: gauges, tid/energi/pris og donut-fordeling
  - `brugere`-tab (`users`) erstattet af ny **`statistik`**-tab 📊 — viser månedlige totaler per bruger, leaderboard og donut side om side i to-kolonne layout
  - Tab-rækkefølge i `localStorage` opgraderes automatisk — ukendte IDs filtreres og nye tilføjes

---

## [2.6.1] - 2026-03-08

## [2.4.1] - 2026-03-03

### Fixed

- **`__init__.py` — Tidsmåling forkert ved brugerskift** (`_handle_user_change`):
  - `self.last_time` blev ikke nulstillet inden ny bruger startede akkumulering
  - Første delta for ny bruger inkluderede tid fra forrige brugers session (phantom-tid)
  - Fix: `self.last_time = now` sættes nu inde i `_handle_user_change` ved hvert brugerskift

- **`__init__.py` — Akkumulerende deltas ved 60s polling** (`_async_update_data`):
  - `self.last_time` blev aldrig opdateret efter `_calculate_deltas()` i polling-løkken
  - Resulterede i voksende delta-vinduer: poll #1 = 60s, poll #2 = 120s, poll #3 = 180s osv.
  - Fix: `self.last_time = now` tilføjet efter `_calculate_deltas()` i `_async_update_data`

- **`websocket.py` — WS-forbindelse crashede ved gem af konfiguration** (`ws_save_config`):
  - `async_update_entry()` triggede `add_update_listener` → `async_reload()` synkront
  - Integration unloadede mens WebSocket-svaret endnu ikke var sendt → panel frøs
  - Fix: `connection.send_result()` sendes først, reload scheduleres via `async_create_task()`

- **`websocket.py` — HA mobil-bruger forsvandt efter reload** (`ws_get_config`):
  - Returnerede `coordinator.user_map` (normaliseret — `ha_user` smidt væk)
  - Fix: Returnerer nu raw `entry.options` så `ha_user` dict-værdier bevares

- **`config_flow.py` — `AttributeError` ved åbning af optionsflow** (`OptionsFlow`):
  - `OptionsFlow.__init__` satte `self.config_entry` som HA 2024+ har gjort til read-only property
  - Fix: `__init__` fjernet — HA injekterer `config_entry` automatisk via base-klassen

- **`panel.py` — "Removing unknown panel" i loggen ved reload**:
  - `_panel_registered` flag overlevede integration-reload → `async_register_panel()` sprang over
  - Efterfølgende unload kaldte `async_remove_panel()` på et panel der ikke eksisterede
  - Fix: `async_unregister_panel()` nulstiller nu altid `_panel_registered = False`

- **`manifest.json` — Forældet `influxdb==5.3.2` requirement fjernet**:
  - Integration bruger udelukkende `aiohttp` til InfluxDB-kommunikation (siden v2.0.0)
  - `influxdb` Python-pakken var aldrig i brug og kunne forårsage installationsfejl

### Changed

- **`pc-user-statistics-panel.js` — Tab-ikoner gjort større og centreret**:
  - Ikon-størrelse: `18px` → `30px`
  - Gap mellem ikon og label: `2px` → `5px`
  - Tab-padding: `10px/14px` → `14px/20px`
  - Tabs centreret i stedet for venstre-aligned (`justify-content: center`)

---

## [2.4.0] - 2026-03-02

### Added

- **Persistent `aiohttp.ClientSession`** (`__init__.py`):
  - Én HTTP-session oprettes ved setup og genbruges til alle InfluxDB-kald
  - Lukkes rent i `async_shutdown()` ved integration-unload
  - Eliminerer overhead fra gentagne session-oprettelser

- **Smart tab-aware polling** (`pc-user-statistics-panel.js`):
  - `_loadForTab()` bruges i 30s polling — henter kun data relevant for aktiv tab
  - Historik- og konfigurationstabs auto-refreshes aldrig
  - `_load()` bruges kun ved første connect og manuel Opdater-knap

- **`async_track_state_change_event`** (`__init__.py`):
  - Erstatter global `EVENT_STATE_CHANGED` bus
  - HA filtrerer events på kilden — langt mere effektivt

- **`async_shutdown()`** (`__init__.py`):
  - Lukker persistent HTTP-session rent ved integration-unload

### Fixed

- Monthly data race condition: snapshot tages før InfluxDB-load, merges efter
- `_query_history` i `websocket.py` genbruger nu koordinatorens persistente session

---

## [2.3.2] - 2026-03-02

### Fixed

- Mobil-responsivt CSS: tab-labels skjules på skærme under 600px
- Notifikations-layout optimeret til mobilvisning
- Diverse CSS-justeringer for bedre mobiloplevelse

---

## [2.3.1] - 2026-03-01

### Fixed

- Lovelace resource registrering fejlede med HA 2024.x API-ændringer
  - `hass.data["lovelace"].resources` erstattet med `hass.data["lovelace_resources"]`
  - Fallback til ældre API for bagudkompatibilitet
- Panel registreret med `module_url` (ES module) i stedet for `js_url`

---

## [2.3.0] - 2026-03-01

### 🎉 Major Feature Release — Custom Panel & Notification System

### Added

- **Custom Sidebar Panel** (`panel.py` + `frontend/pc-user-statistics-panel.js`)
  - Full-featured vanilla JS panel registered in HA sidebar
  - Shadow DOM, no external imports — zero dependency on Lit or other frameworks
  - Automatic dark/light theme detection via `hass.themes.darkMode`
  - 6 tabs: Statistik, Brugere, Notifikationer, Historik, Konfiguration, Admin
  - Drag-and-drop tab reordering saved in `sessionStorage`

- **Live Header**
  - Pulserende ring-animation når en bruger spiller (sonar-effekt)
  - Halvcirkel watt-gauge med live strømforbrug opdateret fra HA state
  - Gradient header-baggrund under aktiv session
  - Farveskala grøn → gul → rød baseret på watt-belastning

- **Leaderboard** (Statistik-tab)
  - Månedlig rangering med 🥇🥈🥉 medaljer
  - Animerede søjler med cubic-bezier
  - Guld-gradient-ramme til #1-pladsen

- **Notification System** (`store.py`, `notification_manager.py`)
  - Persistent storage i `.storage/pc_user_statistics.notifications`
  - 4 premade regler (alle deaktiveret som standard)
  - Opret/rediger/slet egne regler
  - Anti-spam, test-knap, template-variabler: `{user}`, `{time}`, `{cost}`

- **Historik-tab**: SVG søjlediagram, daglige totaler, 30 dage, lazy-load
- **Konfiguration-tab**: Rediger entity IDs og bruger-mappings direkte i UI
- **WebSocket API** (`websocket.py`): 11 kommandoer

### Changed

- Entity IDs er nu dynamiske — læses fra `config_entry.data`
- Admin-only panel (`require_admin=True`), Lovelace cards tilgængelige for alle

---

## [2.0.2] - 2026-03-01

### Fixed

- `MonthlyCostSensor`: `TOTAL_INCREASING` → `TOTAL` (HA 2024+ krav for `MONETARY`)
- Tilføjet manglende konstanter til `const.py`: `CONF_USER_MAPPINGS`, `CONF_TRACKED_USERS`, `DEFAULT_USER_MAP`, `DEFAULT_USERS`

---

## [2.0.1] - 2026-03-01

### Fixed

- JS `SyntaxError: Invalid or unexpected token` — escaped backticks renset ud

---

## [2.0.0] - 2026-01-11

### 🎉 Major Release — Complete Restructure

- Integration omdøbt: `spille_pc_statistik` → `pc_user_statistics`
- Fuld device-struktur: Hub device + per-bruger devices med `via_device`
- Silver quality scale: type hints, device classes, `has_entity_name = True`
- 100-point FIFO write buffer med 3 retry-forsøg
- Config flow med InfluxDB-validering

---

## [1.0.8] - 2025-12-24

### Changed

- Default InfluxDB database: `"stroemforbrug"` → `"homeassistant"`

---

## [1.0.0] - 2025-09-15

### Added

- Initial release — strømforbrug, tid og pris per bruger via InfluxDB
