# Inbildningsportalen

En högst informell kompetensresa med kunskapstest, topplistor och betydligt mer självförtroende än högskolepoäng.

Live: <https://apothictech.se/inbildningsportalen/>

## Innehåll

- `portal/` – startsidan, kursfilter och samlade topplistor.
- `quizzes/` – fristående webbquiz och tillhörande bilder.
- `backend/pharmatest_server.py` – gemensamt leaderboard-API med TOML-lagring.
- `deploy/pharmatest.service` – användartjänsten som kör API:t.
- `deploy/Caddyfile.example` – endast de Caddy-handlers som portalen behöver.

Kurserna är PharmaTest, Författningstestet, Galeniklabbet, Farmakognosiprovet, RiskLab, DosLab och Pungdjursprovet.

## Lokal kontroll

```sh
python3 backend/pharmatest_server.py --self-test
python3 -m http.server 8080 --directory portal
```

Quizsidorna kan på motsvarande sätt öppnas från respektive katalog under `quizzes/`. De förväntar sig leaderboard-API:t på samma origin i drift.

## Serverlayout

Den nuvarande installationen på `192.168.32.186` använder:

- `/srv/apothictech-site/inbildningsportalen/` för portalens livefiler.
- `/srv/apothictech-site/<quiznamn>/` för respektive quiz.
- `/home/nichlas/pharmatest/pharmatest_server.py` för leaderboard-API:t.
- `pharmatest.service` som systemd-användartjänst på port 8798.

Resultatfiler som `scores.toml` och `*-scores.toml` är driftsdata och ska inte versionshanteras. Serverns fullständiga Caddyfile hör till hela apothictech.se-installationen och ingår därför inte; det avgränsade exemplet innehåller portalens nödvändiga routes.
