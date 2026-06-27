# ADR 0022: Redis för rate limiting och caching

## Status
Accepted

## Context
ADR 0008 låste in kravet på per-användare rate limiting och globalt kostnadstak, men lämnade implementationsmekanismen öppen ("en enkel counter med tidsfönster"). Tre konkreta behov har identifierats sedan dess:

1. **Per-user rate limiting** — max antal pipeline-körningar/timme per `user_id` (ADR 0008).
2. **Global kostnadsbevakning** — ackumulerad Claude API-kostnad denna månad, med varningströskel innan budgeten (~5–10 USD/mån) nås.
3. **Cache mellan Fetcher och Embedder** — JobTech/Riksdagen/ENTSO-E pollas troligen upprepat för samma bevakning. Utan cache re-embeddas identisk data i onödan och externa API:er belastas mer än nödvändigt.

Att implementera detta som SQL-tabeller (Postgres) kräver egen race-condition-hantering för atomära increment/decrement och manuell TTL-städning (cron-jobb eller liknande).

## Decision
Använd Redis för:
- **Rate limiting**: `INCR` + `EXPIRE` per `user_id` + tidsfönster (atomärt, ingen race condition).
- **Globalt kostnadstak**: en global counter i Redis för ackumulerad modellkostnad, läses av innan varje Claude API-anrop.
- **Cache**: rådata från Fetcher cachas med kort TTL (nyckel = källa + bevaknings-id), så Embedder/Analyzer slipper bearbeta identisk data igen. Cache-miss/hit kan även användas som signal i schema-drift-detektionen (ADR 0006) — om cachat svar skiljer sig strukturellt från nytt svar, flagga.

Persisterade bevakningar per användare (ADR 0005) ligger fortsatt i Postgres — Redis ersätter inte relationsdata, bara korttidstillstånd och räknare.

## Alternatives considered
- **SQL-counter (Postgres) för rate limiting** — fungerar, men kräver `SELECT ... FOR UPDATE` eller liknande för att undvika race conditions vid samtidiga requests, plus manuell TTL/cleanup-logik. Mer kod, mer att underhålla för samma resultat.
- **In-memory dict i applikationsprocessen** — enklast möjliga, men fungerar inte vid flera processer/instanser (delar inte state), och allt nollställs vid omstart.
- **Ingen cache, alltid färsk fetch** — enklast, men ineffektivt givet att flera bevakningar troligen överlappar i tid och källa; ökar onödigt antal externa API-anrop mot JobTech/Riksdagen/ENTSO-E.

## Consequences
- **Lättare:** atomära operationer (`INCR`/`EXPIRE`) löser rate limiting utan egen concurrency-hantering; cache minskar onödig embedding-bearbetning och extern API-belastning; tydlig separation mellan "tillstånd som måste persisteras" (Postgres) och "korttidsdata/räknare" (Redis) — bra arkitekturstory i intervju.
- **Svårare:** introducerar ytterligare en extern beroende/komponent att driftsätta och övervaka (kopplar till ADR 0007, observability — Redis-relaterade fel bör synas i tracing, inte tystas). Data i Redis är inte garanterat persistent vid krasch om inte persistens konfigureras explicit — adekvat här eftersom inget i Redis är "source of truth", men måste vara en medveten avgränsning, inte en miss.
- Kräver beslut om hosting: Redis Cloud free tier (~30MB) räcker för denna skala och håller sig inom budgeten, alternativt egen container i samma compose-stack om Docker redan används.
