# RAG locale con Gemini File Search

Web UI Streamlit (`app.py`) e CLI (`rag_chat.py`) per caricare documenti in un File Search Store di Gemini e fare RAG.

## Requisiti
- Python 3.11+
- GEMINI_API_KEY impostata nell'ambiente.

## Setup locale
```bash
pip install -r requirements.txt
setx GEMINI_API_KEY "LA_TUA_CHIAVE"  # su Windows, poi riapri PowerShell
# oppure per la sessione: $env:GEMINI_API_KEY="LA_TUA_CHIAVE"
```

## Avvio web UI (Streamlit)
```bash
cd c:\Users\probl\iCloudDrive\Progetti\rag_gemini
streamlit run app.py
```

## Avvio CLI
```bash
cd c:\Users\probl\iCloudDrive\Progetti\rag_gemini
py -3 rag_chat.py
```

## Deploy su Streamlit Cloud
1. Metti il codice su GitHub (aggiungi `store_name.txt` al `.gitignore` se non vuoi committarlo).
2. In Streamlit Cloud crea una nuova app puntando al repo e al file `app.py`.
3. Imposta la variabile d’ambiente `GEMINI_API_KEY` nelle Secrets/Environment Variables.
4. Deploy: otterrai un URL pubblico per condividere l’app.

## Note sullo store
- `store_name.txt` salva il nome dello store per riuso. Per un nuovo store, usa il pulsante “Crea nuovo store vuoto” nella UI, oppure elimina/azzera `store_name.txt` prima del run.
