from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import google.genai as genai
from google.genai.types import DocumentState, FileSearch, Tool

STORE_FILE = Path("store_name.txt")
MODEL_NAME = "gemini-2.5-flash"


def load_api_key() -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Errore: variabile d'ambiente GEMINI_API_KEY mancante.", file=sys.stderr)
        sys.exit(1)
    return api_key


def get_or_create_store() -> str:
    if STORE_FILE.exists():
        name = STORE_FILE.read_text(encoding="utf-8").strip()
        if name:
            return name
    client = get_client()
    store = client.file_search_stores.create(config={"display_name": "local-rag-store"})
    store_name = store.name or ""
    STORE_FILE.write_text(store_name, encoding="utf-8")
    return store_name


def upload_document(store_name: str) -> None:
    path = input("Percorso file da caricare: ").strip().strip('"').strip("'")
    if not path:
        print("Percorso non valido.")
        return
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        print("File non trovato.")
        return
    print("Caricamento in corso...")
    client = get_client()
    op = client.file_search_stores.upload_to_file_search_store(
        file_search_store_name=store_name,
        file=str(file_path),
    )
    print(f"Upload avviato: {op.name}. Attendo completamento...")
    doc_name = wait_for_upload(op)
    if not doc_name:
        return
    print(f"File caricato come {doc_name}. Attendo che diventi ACTIVE...")
    wait_for_active(doc_name)
    print("File pronto per le ricerche.")


def wait_for_upload(op: genai.types.UploadToFileSearchStoreOperation, timeout: float = 300.0, interval: float = 2.0) -> str | None:
    client = get_client()
    start = time.time()
    current = op
    while True:
        if current.done:
            if current.error:
                print(f"Upload fallito: {current.error}")
                return None
            if current.response and current.response.document_name:
                return current.response.document_name
            print("Upload completato ma senza document_name.")
            return None
        if time.time() - start > timeout:
            print("Timeout in attesa del completamento dell'upload.")
            return None
        time.sleep(interval)
        current = client.operations.get(operation=current)


def wait_for_active(doc_name: str, timeout: float = 300.0, interval: float = 2.0) -> None:
    client = get_client()
    start = time.time()
    while True:
        doc = client.file_search_stores.documents.get(name=doc_name)
        state = getattr(doc.state, "name", str(doc.state)) if doc.state is not None else ""
        if state == DocumentState.STATE_ACTIVE.name:
            return
        if state == DocumentState.STATE_FAILED.name:
            print("Elaborazione del documento fallita.")
            return
        if time.time() - start > timeout:
            print("Timeout in attesa che il file diventi ACTIVE.")
            return
        time.sleep(interval)


def ask_question(store_name: str, question: str | None = None) -> None:
    if question is None:
        question = input("Domanda: ").strip()
    if not question:
        print("Domanda vuota.")
        return
    client = get_client()
    tool = Tool(file_search=FileSearch(file_search_store_names=[store_name]))
    print("Interrogo i documenti...")
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=question,
            config={"tools": [tool]},
        )
    except Exception as exc:
        print(f"Errore durante la generazione: {exc}")
        return
    print("\nRisposta:\n")
    print(response.text if hasattr(response, "text") else response)


def ask_questions_loop(store_name: str) -> None:
    print("Modalità domande: lascia vuoto e premi Invio per tornare al menu.")
    while True:
        question = input("Domanda: ").strip()
        if not question:
            print("Torno al menu.")
            return
        ask_question(store_name, question)


_CLIENT: genai.Client | None = None


def get_client() -> genai.Client:
    global _CLIENT
    if _CLIENT is None:
        load_api_key()
        _CLIENT = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _CLIENT


def main() -> None:
    get_client()
    store_name = get_or_create_store()
    menu = {
        "1": ("Carica documento", upload_document),
        "2": ("Fai domande (puoi farne più di una)", ask_questions_loop),
        "3": ("Esci", None),
    }
    while True:
        print("\n--- Menu ---")
        for key, (label, _) in menu.items():
            print(f"{key}. {label}")
        choice = input("Seleziona un'opzione: ").strip()
        if choice == "3":
            print("Uscita.")
            break
        action = menu.get(choice)
        if not action:
            print("Scelta non valida.")
            continue
        _, func = action
        func(store_name)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
