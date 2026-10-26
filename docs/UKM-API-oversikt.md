# Hva finnes i UKMs offentlige API?

Kontrollert mot UKMs offentlige dokumentasjon og kildekode 26. oktober 2026. Kilder: [UKMapi_public](https://github.com/UKMNorge/UKMapi_public), [nettside-API-ets dokumentasjon](https://github.com/UKMNorge/UKMapi_public/blob/master/nettside/README.md) og [de faktiske rutene](https://github.com/UKMNorge/UKMapi_public/tree/master/nettside).

`UKMapi` er PHP-biblioteket. `UKMapi_public` er HTTP-API-et som andre tjenester kan bruke. Denne oversikten beskriver kildekoden; bare rutene som brukes av kalendergeneratoren og innslagsuttrekket er integrasjonstestet her. Eldre ruter kan ha andre svarformater eller være ufullstendige.

## Offentlige nettsidedata

Basisadresse: `https://api.ukm.no`. Parametere sendes etter `?`, for eksempel [innslag for arrangement 9902](https://api.ukm.no/nettside:arrangement_innslag?arrangement_id=9902). ID-en er et eksempel; en gyldig liste kan være tom.

Tabellen dekker alle **23 ruter** i `nettside/`: 22 leseruter som støtter `GET`, samt én skriverute for interesseskjema. Leserutene er deklarert uten autentisering i kildekoden. At en rute er offentlig, sier ikke at alle feltene bør lagres videre; prosjektet eksporterer bare de avtalte innslagsfeltene.

| Endepunkt | Parametere | Hva det gir |
| --- | --- | --- |
| `/nettside:alle_fylker` | Ingen | Fylkes-ID, navn, lenke, aktiv-status og markering av tekniske/testfylker. |
| `/nettside:alle_kommuner` | Ingen | Kommuner/bydeler, ID, navn, fylkestilknytning og lenke. |
| `/nettside:alle_kommende_arrangementer` | Ingen | Kommende og pågående synlige arrangementer. Kildekoden søker i sesongene fra året før til to år frem. |
| `/nettside:alle_arrangementer` | `season`; valgfritt `type` | Synlige arrangementer i en sesong. `type` kan være `kommune`, `fylke` eller `land`. Sesong fra og med 2020. |
| `/nettside:single_arrangement` | `path` | Ett arrangement: ID, navn, beskrivelse, sted, start/slutt, påmeldingsfrister, nivå, kommuner/fylke og påmeldingslenker. |
| `/nettside:arrangementer_fylke` | `fylke_id` | Arrangementer som tilhører et fylke. |
| `/nettside:arrangementer_kommune` | `kommune_id` | Arrangementer som tilhører en kommune/bydel. |
| `/nettside:arrangement_banner` | `arrangement_id` | Bannerbilde, tilgjengelige bildestørrelser og bildeposisjon. |
| `/nettside:arrangement_program_new` | `arrangement_id` | Programhendelser med navn, beskrivelse og ordnede `items`, blant annet innslag og aktiviteter. |
| `/nettside:arrangement_program` | `arrangement_id` | Eldre programformat. Bruk normalt `arrangement_program_new` ved en ny integrasjon. |
| `/nettside:arrangement_innslag` | `arrangement_id` | Offentlig påmeldte innslag: ID, navn, type, sjanger, beskrivelse, område og publiserte personnavn. Dette brukes av `paameldte.json`. |
| `/nettside:arrangement_innlegg` | `arrangement_id`; valgfritt `category` | Innlegg/artikler som tilhører arrangementet, med eventuell kategorifiltrering. |
| `/nettside:arrangement_bilder` | `arrangement_id` | Arrangementsbilder og størrelser/filadresser. |
| `/nettside:arrangement_bilder_context` | `arrangement_id` | Bilder med tilknytning til innslag, programhendelser og geografisk område. |
| `/nettside:arrangement_filmer` | `arrangement_id` | Arrangementsfilmer med blant annet tittel, beskrivelse, miniatyr og avspillings-/innbyggingslenker. |
| `/nettside:arrangement_filmer_context` | `arrangement_id` | Filmer med tilknytning til innslag og programhendelser. |
| `/nettside:innslag_bilder` | `innslag_id`; valgfritt `arrangement_id` | Bilder for ett innslag, eventuelt begrenset til ett arrangement. |
| `/nettside:innslag_filmer` | `innslag_id`; valgfritt `arrangement_id` | Filmer for ett innslag, eventuelt begrenset til ett arrangement. |
| `/nettside:arrangement_kontaktpersoner` | `arrangement_id` | Arrangørenes publiserte kontaktpersoner, med navn, rolle/beskrivelse og tilgjengelig kontaktinformasjon. |
| `/nettside:alle_kontaktpersoner` | Ingen | Kontaktpersoner gruppert på områder, kommuner, fylker og UKM Norge. |
| `/nettside:alle_aktiviteter` | `arrangement_id` | Aktiviteter/workshops med blant annet navn, sted, beskrivelse, kursholder, bilde og program-synlighet. Dokumentasjonen beskriver også tags og tidspunkter. |
| `/nettside:single_aktivitet` | `aktivitet_id` | Detaljer for én aktivitet. Påmeldte personer er uttrykkelig utelatt fra dette offentlige aktivitets-API-et. |
| `/nettside:registrer_interesse` | **POST**: `navn`, `beskrivelse` og minst én av `mobil`/`epost`; valgfritt `arrangor_interesse`, `kommuner` | Sender inn et interesseskjema og oppretter/oppdaterer data. Dette er ikke en lesbar liste over interessenter. Det er ikke kalt av kalenderprosjektet. |

## Hva kan lagres om påmeldte?

Den implementerte eksporten leser kun `arrangement_innslag`, for arrangementene som allerede finnes i kalenderens kommende/pågående datagrunnlag. Den er en liste over innslag og deres offentlig publiserte navn. Den gir ikke et fullstendig register over crew, bak scenen, publikum, aktivitetspåmeldinger eller alle personer i UKM.

I eksporten velges disse feltene eksplisitt:

```json
{
  "id": "123",
  "navn": "Eksempelband",
  "beskrivelse": "Innslagets publiserte beskrivelse.",
  "deltakernavn": ["Offentlig publisert navn"]
}
```

`antall_deltakernavn_i_innslag` teller navneforekomster i innslagene, ikke unike personer. Én person kan være med i flere innslag. En tom liste betyr at den offentlige innslagslisten svarte uten treff; det betyr ikke nødvendigvis at ingen er påmeldt arrangementet.

## Eldre v2-grensesnitt

Repositoryet har også en eldre `/2.0/…`-struktur. Rutene nedenfor er funnet i kildekoden, men er ikke hentet som datakilde for dette prosjektet. Noen er ufullstendige; tilgang må kontrolleres per rute. Beskyttede data er ikke hentet.

| Område | Ruter/kildefiler som finnes | Dokumentasjon/kilde |
| --- | --- | --- |
| Mønstringer | Henting av mønstring med ID, kommune eller fylke. Dokumentasjonen merker samlet liste som ikke implementert. | [Mønstringer](https://github.com/UKMNorge/UKMapi_public/blob/master/v2/monstringer/README.md) |
| Program | Programliste, gruppering per dag og én programhendelse med innslag. | [Program](https://github.com/UKMNorge/UKMapi_public/blob/master/v2/program/README.md) |
| Kontaktpersoner | Kontaktliste og henting av én kontaktperson, under en mønstring. | [Kontaktpersoner](https://github.com/UKMNorge/UKMapi_public/blob/master/v2/kontakter/README.md) |
| Innslag | `list.php`, `findBy.php`, `basisinfo.php`. | [Innslag](https://github.com/UKMNorge/UKMapi_public/tree/master/v2/innslag) |
| Innslagstyper | `innslagtype/list.php`. | [Innslagstyper](https://github.com/UKMNorge/UKMapi_public/tree/master/v2/innslagtype) |
| Filmer | `filmer/list.php`, `filmer/siste.php`. | [Filmer](https://github.com/UKMNorge/UKMapi_public/tree/master/v2/filmer) |
| Konkurranser | `konkurranse/active.php`, `konkurranse/findBy.php`. | [Konkurranser](https://github.com/UKMNorge/UKMapi_public/tree/master/v2/konkurranse) |
| Personer | `personer/list.php`, `personer/meg.php`. `meg.php` inkluderer autentiseringskontroll og er en ufullstendig implementasjon. Brukes ikke i eksporten. | [Personer](https://github.com/UKMNorge/UKMapi_public/tree/master/v2/personer) |

## Andre ruter i repositoryet

Følgende eldre `.api.php`-filer finnes utenfor `nettside/`. Listen viser tilgjengelig kildekode, og er ikke en bekreftelse på at rutene er offentlig lesbare eller operative. Det er ikke gjort live-kall til dem i dette arbeidet. URL-mønsteret er generelt `https://api.ukm.no/<mappe>:<fil>`; enkelte eldre ruter bruker argumenter som en del av stien.

| Gruppe | Filer/rutenavn i kilden | Type innhold |
| --- | --- | --- |
| `post` | `sted` | Postnummer/stedsoppslag, brukt som eksempel i hoveddokumentasjonen. |
| `public` | `arrangement-finder` | Eldre arrangementsoppslag. |
| `video` | `info`, `registrer`, `tv_update` | Videoinfo og registrerings-/oppdateringsfunksjoner. Skrivefunksjoner brukes ikke. |
| `playback` | `file` | Playback-/filfunksjon. |
| `konkurranse` | `status` | Konkurransestatus. |
| `innslag` | `statistikk_oppdater` | Statistikkoppdatering; ikke en eksport av påmeldte. |
| `ekstern` | `v1` | Eldre ekstern integrasjon. |
| `server` | `diskspace`, `ip`, `tilgjengelig`, `tv` | Drifts-/serverfunksjoner, ikke arrangementsinnhold. |
| `protected` | `getAlleDeltakereSvar`, `slettDeltakerSvar`, `transferFilm` | Beskyttede svar- og overføringsfunksjoner. Ingen slike svar eller personopplysninger er hentet. |

Se [hele kildeoversikten](https://github.com/UKMNorge/UKMapi_public) for implementasjonene og [hoveddokumentasjonen](https://github.com/UKMNorge/UKMapi_public/blob/master/README.md) for eldre URL-mønstre.
