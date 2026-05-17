# Almedalskartan

Automatisk uppdatering av Almedalsveckans program, paketerat som en interaktiv karta
och lista byggd av Influera (BLCKR). Bygger om sajten två gånger per dygn från
arrangörsportalens officiella JSON-export och deployar till Netlify.

## Vad finns här

```
.
├── .github/workflows/update.yml   GitHub Actions, körs 06:00 och 18:00 UTC
├── scripts/
│   ├── fetch_program.py           Loggar in via Playwright, hämtar JSON
│   └── build_site.py              Bygger index.html från JSON + template
├── template/
│   ├── template.html              HTML-mall med __DATA__, __LEAFLET_*__ -platshållare
│   ├── leaflet.css                Inlinat Leaflet 1.9.4
│   └── leaflet.js                 Inlinat Leaflet 1.9.4
├── data/
│   ├── program.json               Senaste rå-JSON från portalen (uppdateras av pipeline)
│   └── last_run.json              Metadata om senaste körning
└── index.html                     Färdiga sajten, deployas av Netlify
```

## Setup, steg för steg

### 1. Skapa GitHub-repo

1. Logga in på https://github.com som `odrnaswe`
2. Klicka **+** uppe till höger → **New repository**
3. Repository name: `almedalskartan`
4. Visibility: **Private**
5. Lämna allt annat som standard, klicka **Create repository**

### 2. Ladda upp filerna

Enklast via webbgränssnittet:

1. På den nya repo-sidan, klicka **uploading an existing file** (eller dra-och-släpp-länken)
2. Dra in HELA innehållet i mappen `almedalskartan-repo` (alla undermappar och filer, inklusive `.github`)
3. Commit-meddelande: "Initial setup"
4. Klicka **Commit changes**

Om `.github`-mappen inte kommer med vid drag-och-släpp (vanligt problem) får
du skapa den manuellt: klicka **Add file** → **Create new file** → skriv
`.github/workflows/update.yml` i namn-fältet och klistra in innehållet från
filen lokalt.

### 3. Lägg till hemligheter (Secrets)

1. På repo-sidan, klicka **Settings** (övre menyn)
2. Vänstermenyn: **Secrets and variables** → **Actions**
3. Klicka **New repository secret**
4. Namn: `ALME_USERNAME`, Value: din e-postadress till portalen
5. Klicka **Add secret**
6. Klicka **New repository secret** igen
7. Namn: `ALME_PASSWORD`, Value: ditt lösenord
8. Klicka **Add secret**

### 4. Ge GitHub Actions skrivrättigheter

1. **Settings** → vänstermenyn **Actions** → **General**
2. Skrolla till **Workflow permissions** (längst ner)
3. Välj **Read and write permissions**
4. Klicka **Save**

### 5. Testa workflow manuellt

1. Klicka **Actions** i övre menyn på repo-sidan
2. Vänstermenyn: klicka **Update Almedalskartan**
3. Till höger: klicka **Run workflow** → **Run workflow**-knappen
4. Vänta cirka 1-3 minuter, klicka på den nya körningen
5. Klicka på **update**-jobbet för att se loggen

Om det fungerar ser du i loggen något i stil med:

```
Got JWT (length=XXX)
Got JSON: 6700000 bytes
Raw events: 2398
Normalized events: 2398
Wrote index.html (4.32 MB)
```

Och en ny commit dyker upp i repo:t "Auto-update program data ...".

### 6. Koppla Netlify till repot

1. Logga in på Netlify
2. På din befintliga sajt `marvelous-chaja-89eaf5`, gå till **Site configuration** → **Build & deploy** → **Continuous deployment**
3. Klicka **Link site to a repository** (eller liknande, namnet varierar mellan UI-versioner)
4. Välj **GitHub**, godkänn åtkomst
5. Välj `odrnaswe/almedalskartan`
6. Branch: `main`
7. Build command: lämna tomt
8. Publish directory: `.` (en punkt, betyder repo-roten)
9. Klicka **Deploy site**

Härefter triggar varje commit på `main`-branchen en ny deploy automatiskt.

### 7. Verifiera

1. På GitHub, gå till **Actions**, klicka **Update Almedalskartan**, **Run workflow**
2. När körningen är klar (3 minuter), kolla att en ny commit dykt upp
3. På Netlify, kolla **Deploys**, en ny deploy ska vara på gång
4. När Netlify-deployen är klar, öppna sajten och verifiera att datat är aktuellt

## Felsökning

### Pipeline misslyckas

GitHub skickar mejl till repo-ägaren när en workflow misslyckas. Klicka in på
körningen och se loggen för felmeddelande.

Vanligaste orsakerna:

- **Fel lösenord**: uppdatera `ALME_PASSWORD` i Settings → Secrets
- **Region Gotland har ändrat inloggningsformuläret**: Playwright hittar inte
  rätt input-fält. Mejla mig, jag fixar selectorerna.
- **Token-utgång under körning**: ovanligt, pipeline tar 30-60 sekunder och
  token är giltig 2 timmar.

### Ändra schemat

Redigera `.github/workflows/update.yml`, raden `- cron: '0 6,18 * * *'`.
Format är UTC-tid. Aktuell setup: 06:00 och 18:00 UTC = 07:00 och 19:00
svensk sommartid (08:00 och 20:00 vintertid).

### Trigga manuellt

GitHub → **Actions** → **Update Almedalskartan** → **Run workflow**.

## Säkerhet

Lösenordet lagras som GitHub Secret, krypterat och åtkomligt enbart för
workflows som körs i detta repo. När du byter lösenord i portalen, uppdatera
även Secret:

1. Settings → Secrets and variables → Actions
2. Klicka på `ALME_PASSWORD`
3. Klicka **Update**, klistra in nya lösenordet

## Frågor

Bygg-arkitekt: Claude / Anthropic, för Influera. Kontakta Sandro på BLCKR.
