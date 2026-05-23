# Instruktioner: uppdatera scripts/build_site.py

Den nya template.html (template_step11.html) innehåller **ingen `__WEATHER_DATA__`-platshållare** längre, eftersom vädret hämtas i webbläsaren direkt från SMHI.

Det betyder att din `build_site.py` inte längre behöver:

1. Anropa SMHI-API:et
1. Ersätta `__WEATHER_DATA__` med JSON-data

## Vad du ska göra

Öppna `scripts/build_site.py` på GitHub och **ta bort** följande:

- Alla rader som anropar SMHI (`fetch_smhi_weather` eller liknande funktion)
- Alla rader som ersätter `__WEATHER_DATA__` i template-strängen (typ `template.replace('__WEATHER_DATA__', ...)`)
- Eventuell import av `requests` eller annat som bara används för väder

Behåll allt annat (template-läsning, datalästning, `__DATA__`-ersättning, `__LEAFLET_CSS__`/`__LEAFLET_JS__`-ersättning).

## Exempel på vad som troligen finns och ska bort

```python
# DESSA RADER SKA BORT eller kommenteras ut:
weather_data = fetch_smhi_weather()
html = html.replace('__WEATHER_DATA__', json.dumps(weather_data))

# OCH FUNKTIONEN:
def fetch_smhi_weather():
    ...
```

## Om du är osäker

Ladda upp `scripts/build_site.py` till Claude (eller mig i nästa chatt) och be om en uppdaterad version. Det är 5 minuters jobb.

## Alternativt: lämna build_site.py orörd

Om du lämnar `build_site.py` som den är så händer detta:

- Skriptet försöker ersätta `__WEATHER_DATA__` i template:n
- Eftersom platshållaren inte finns, händer inget och `replace()` är en no-op
- Bygget fungerar ändå

Så det är inte tekniskt nödvändigt att uppdatera build_site.py för att sajten ska fungera. Det är bara renare kod och något mindre overhead per bygge.