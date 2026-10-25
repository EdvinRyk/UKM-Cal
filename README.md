# UKM i kalenderen din

Én iCalendar-feed for hvert av Norges 15 fylker og én for nasjonale UKM-arrangementer. Alle kommende og pågående offentlige arrangementer i UKMs kilder tas med, også neste kalenderår. Det er ingen egen øvre datogrense i generatoren.

Valgt repository: [EdvinRyk/UKM-Cal](https://github.com/EdvinRyk/UKM-Cal). Publiseringsadressen etter aktivering av GitHub Pages er `https://edvinryk.github.io/UKM-Cal/`.

**Løsningen er publisert på [GitHub Pages](https://edvinryk.github.io/UKM-Cal/), med daglig oppdatering via GitHub Actions. Nettsiden har fast mørk modus.**

## Publisering på GitHub

1. Bruk det offentlige repositoryet `EdvinRyk/UKM-Cal` med standardgren `main`.
2. Legg inn hele innholdet i denne prosjektmappen i repositoryets rot, inkludert `.github/`, `ukm_calendar/`, `tests/`, `pyproject.toml` og `generated/`. En ZIP-fil må pakkes ut før innholdet legges inn. Selve ZIP-filen starter ingen jobb.
3. Åpne **Settings → Pages → Build and deployment**, og velg **GitHub Actions** som publiseringskilde.
4. Under **Settings → Actions → General → Workflow permissions** må jobbene kunne skrive repository-innhold. Oppdateringsjobben bruker repositoryets vanlige `GITHUB_TOKEN`; ingen egen API-nøkkel eller Google-tilgang trengs. Standardgrenen må tillate at jobben lagrer genererte data med en commit. Dersom organisasjonen blokkerer dette, må repositoryets eksisterende regler tilpasses av eieren.
5. Åpne **Actions → Oppdater og publiser UKM-kalendere → Run workflow**. Første automatisk utløste kjøring kan feile hvis Pages ikke var aktivert ennå; kjør den da manuelt etter trinn 3.
6. Når både `build` og `deploy` er grønne, åpner du adressen i **Settings → Pages**. Nettstedet viser alle 16 abonnementslenkene og knapper for Google Kalender.

Den faktiske adressen hentes automatisk fra GitHub Pages, også ved et konfigurert eget domene. Ingen adresser trenger å endres i koden.

Oppdatering er satt til **04.17 UTC hver dag** (05.17 eller 06.17 norsk tid, avhengig av sommertid). GitHub kan forsinke planlagte jobber. Hver vellykkede bygging lagrer nytt datagrunnlag og oppdateringsstatus i repositoryet, også når arrangementsinnholdet er uendret. Det gir historikk og løpende repository-aktivitet. Feil vises som en mislykket Actions-kjøring; forrige publiserte nettsted beholdes.

Kjøring av workflow fra en fork kan måtte aktiveres under Actions først. GitHub kan deaktivere planlagte jobber etter langvarig inaktivitet: se [GitHubs dokumentasjon](https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-workflow-runs/disabling-and-enabling-a-workflow).

## Bruke kalenderne

Åpne det publiserte nettstedet og velg **Legg til i Google Kalender**. Knappen viser riktig HTTPS-lenke og åpner en veiledning: kopier lenken, åpne Googles **Fra nettadresse**, lim inn lenken og velg **Legg til kalender**. Dette bruker [Googles dokumenterte abonnementsflyt](https://support.google.com/calendar/answer/37100?hl=no), og unngår snarveier med `cid` som Google kan avvise. Du kan også bruke **Kopier lenke** på kalenderkortet.

Legg til et nytt abonnement i en nettleser på en datamaskin. Google Kalender-appen kan vise abonnementet etterpå, men støtter ikke selve opprettelsen via nettadresse.

En enkelt nedlasting og import av en `.ics`-fil gir en engangskopi. Bruk abonnement for automatiske oppdateringer. Google avgjør selv når abonnementet hentes på nytt; daglig generering gir ikke en garanti for at endringen vises samme dag i Google.

Faste kalenderstier:

| Kalender | Fil under nettstedets rot |
| --- | --- |
| Agder | `kalendere/agder.ics` |
| Akershus | `kalendere/akershus.ics` |
| Buskerud | `kalendere/buskerud.ics` |
| Finnmark | `kalendere/finnmark.ics` |
| Innlandet | `kalendere/innlandet.ics` |
| Møre og Romsdal | `kalendere/moreogromsdal.ics` |
| Nordland | `kalendere/nordland.ics` |
| Oslo | `kalendere/oslo.ics` |
| Rogaland | `kalendere/rogaland.ics` |
| Telemark | `kalendere/telemark.ics` |
| Troms | `kalendere/troms.ics` |
| Trøndelag | `kalendere/trondelag.ics` |
| Vestfold | `kalendere/vestfold.ics` |
| Vestland | `kalendere/vestland.ics` |
| Østfold | `kalendere/ostfold.ics` |
| Nasjonale arrangementer | `kalendere/nasjonalt.ics` |

Den nasjonale kalenderen viser bare arrangementer med UKM-nivå `land`. Den er et gyldig, tomt abonnement når ingen slike arrangementer er publisert fremover. Nasjonale arrangementer legges ikke automatisk i fylket der de fysisk finner sted. Lokale og regionale arrangementer som gjelder flere fylker, tas med i hvert aktuelt fylke.

## Kjøre og teste lokalt

Krever Python 3.11 eller nyere. Generatoren bruker bare standardbiblioteket. Kommandoene kjøres i prosjektmappen:

```sh
python3 -m ukm_calendar
python3 -m http.server 8000 --bind 127.0.0.1 --directory generated/site
```

Åpne `http://127.0.0.1:8000/` for forhåndsvisning. Google-knappene er deaktivert ved lokal forhåndsvisning fordi Google trenger en offentlig adresse. iCal-filene kan lastes ned lokalt.

Angi offentlig adresse ved manuell generering for et allerede publisert nettsted:

```sh
python3 -m ukm_calendar --base-url https://edvinryk.github.io/UKM-Cal/
```

Bruk et isolert miljø for testverktøyene:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install '.[test]'
.venv/bin/python -m unittest discover -s tests -v
```

Testene bruker lagrede, offentlige eksempler fra UKM og trenger ikke nettverk. De kontrollerer paginering, neste år, fylkesfordeling, festivalmaler, nasjonalt nivå, norsk sommertid, avlysninger, stabile ID-er, endringer/fjerning, UTF-8, lange beskrivelser og at mislykkede bygginger bevarer forrige utgivelse. Den uavhengige `icalendar`-parseren kontrollerer også alle faktisk genererte filer mot datagrunnlaget.

## Kilder og driftsregler

- Offentlig søkeindeks: `events_prod`, brukt av [ukm.no/arrangement](https://www.ukm.no/arrangement). Alle resultatsider hentes og kontrolleres mot totalt antall treff. Nettleserens offentlige søkelegitimasjon oppdages fra UKMs egne ressurser ved hver kjøring; ingen privat nøkkel lagres.
- [Offentlig UKM-API og dokumentasjon](https://github.com/UKMNorge/UKMapi_public/blob/master/nettside/README.md): `nettside:alle_fylker`, `nettside:alle_kommende_arrangementer` og `nettside:single_arrangement?path=…` under `https://api.ukm.no/`. API-listen supplerer søket, blant annet for nasjonale arrangementer. API-listen har selv en begrensning fra forrige sesong til to år frem; søket hentes uten årsfiltret, slik at kildens tilgjengelige arrangementer lenger frem også tas med.
- Alle aktuelle arrangementssider leses. Full beskrivelse, arrangementsinformasjon, offentlige kontaktkort, påmeldingslenker og lenker til program og medier tas med. Separate nyhetsartikler åpnes ikke. Bilder/video beholdes som lenker. Navigasjon og generell bunntekst utelates.
- API-ets `*_date.date` inneholder norsk klokkeslett selv om sonen er merket `UTC`. Dette er kontrollert mot synlige vinter- og sommertider. Datoene tolkes som `Europe/Oslo` og skrives som korrekte UTC-tider i iCalendar. Manglende klokkeslett gir heldagsoppføring med eksklusiv sluttdato. Tvetydige eller ugyldige tider ved sommertidsovergang stopper publisering for kontroll.
- API-ets `fake`-fylker (testområder) utelates. Nasjonale arrangementer identifiseres etter `type=land` også når deres tekniske fylke er markert `fake`.
- UID bygger på UKMs arrangements-ID. Endret innhold gir økt `SEQUENCE` og nytt `LAST-MODIFIED`; uendret innhold beholder begge. Identiteten overlever navneendringer og bytte av URL. `TRANSP:TRANSPARENT` lar abonnementsarrangementer vises uten å blokkere din ledige tid.
- Avlysning krever et uttrykkelig flagg/status, tittel som «AVLYST: …» eller en uttrykkelig avlysningsmelding på siden. Manglende arrangement i en komplett, vellykket uthenting fjernes. Feil, ukjent fylke, endret kildeformat eller ufullstendig paginering stopper publisering.
- Uventet tom kilde, eller tømming av en kalenderutgivelse med fortsatt aktive hendelser, stopper oppdateringen. Etter manuell bekreftelse på at kilden faktisk er tom kan `--allow-empty` brukes lokalt. Avsluttede arrangementer fjernes normalt ved neste kjøring.
- Hele utgivelsen bygges i en midlertidig mappe og kontrolleres før den erstatter `generated/`. GitHub publiserer den komplette `generated/site` som én Pages-utgivelse. Nettstedet eksponerer bare kalenderfiler og oppdateringsstatus; datagrunnlaget ligger i repositoryet.

## Genererte filer

- `generated/site/index.html`: abonnementsoversikt.
- `generated/site/kalendere/*.ics`: 16 kalenderfiler.
- `generated/site/status.json`: siste vellykkede generering, kildeomfang og antall arrangementer.
- `generated/data/latest.json`: siste vellykkede offentlige kilde- og arrangementsdata.
- `generated/data/events-state.json`: stabile revisjoner og tidsstempler.
- `generated/data/status.json`: samme byggestatus som på nettstedet.

Dette er en uavhengig kalendergenerator. Innholdet kommer fra UKMs offentlige sider. Faktiske hendelsesopplysninger og publiserte tekster tilhører sine respektive rettighetshavere.
