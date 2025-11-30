from __future__ import annotations

import os
import base64
import tempfile
import mimetypes
import time
from pathlib import Path

import streamlit as st
import google.genai as genai
from google.genai.types import DocumentState, FileSearch, Tool

STORE_FILE = Path("store_name.txt")
MODEL_NAME = "gemini-2.5-flash"
IMAGE_MODEL = "imagen-3.0"


@st.cache_resource
def get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        st.stop()
    return genai.Client(api_key=api_key)


def get_or_create_store(client: genai.Client) -> str:
    env_store = os.environ.get("STORE_NAME")
    if env_store:
        return env_store
    if STORE_FILE.exists():
        name = STORE_FILE.read_text(encoding="utf-8").strip()
        if name:
            return name
    store = client.file_search_stores.create(config={"display_name": "local-rag-store"})
    store_name = store.name or ""
    STORE_FILE.write_text(store_name, encoding="utf-8")
    return store_name


def wait_for_upload(client: genai.Client, op: genai.types.UploadToFileSearchStoreOperation, timeout: float = 300.0, interval: float = 2.0) -> str | None:
    start = time.time()
    current = op
    while True:
        if current.done:
            if current.error:
                st.error(f"Upload fallito: {current.error}")
                return None
            if current.response and current.response.document_name:
                return current.response.document_name
            st.error("Upload completato ma senza document_name.")
            return None
        if time.time() - start > timeout:
            st.error("Timeout in attesa del completamento dell'upload.")
            return None
        time.sleep(interval)
        current = client.operations.get(operation=current)


def wait_for_active(client: genai.Client, doc_name: str, timeout: float = 300.0, interval: float = 2.0) -> bool:
    start = time.time()
    while True:
        doc = client.file_search_stores.documents.get(name=doc_name)
        state = getattr(doc.state, "name", str(doc.state)) if doc.state is not None else ""
        if state == DocumentState.STATE_ACTIVE.name:
            return True
        if state == DocumentState.STATE_FAILED.name:
            st.error("Elaborazione del documento fallita.")
            return False
        if time.time() - start > timeout:
            st.error("Timeout in attesa che il file diventi ACTIVE.")
            return False
        time.sleep(interval)


def upload_document(client: genai.Client, store_name: str, uploaded_file) -> None:
    ext = Path(uploaded_file.name).suffix
    mime_type = uploaded_file.type or mimetypes.guess_type(uploaded_file.name)[0] or "application/octet-stream"
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(uploaded_file.getbuffer())
        tmp_path = tmp.name
    op = client.file_search_stores.upload_to_file_search_store(
        file_search_store_name=store_name,
        file=tmp_path,
        config={"mime_type": mime_type},
    )
    with st.status("Caricamento in corso...", expanded=True) as status:
        doc_name = wait_for_upload(client, op)
        if not doc_name:
            status.update(label="Upload fallito", state="error")
            return
        status.write(f"File caricato come {doc_name}. Attendo ACTIVE...")
        if wait_for_active(client, doc_name):
            status.update(label="File pronto", state="complete")


def ask_question(client: genai.Client, store_name: str, question: str) -> str:
    tool = Tool(file_search=FileSearch(file_search_store_names=[store_name]))
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=question,
        config={"tools": [tool]},
    )
    return response.text if hasattr(response, "text") else str(response)


def reset_store(client: genai.Client) -> str:
    store = client.file_search_stores.create(config={"display_name": "local-rag-store"})
    store_name = store.name or ""
    STORE_FILE.write_text(store_name, encoding="utf-8")
    st.session_state["store_name"] = store_name
    return store_name


def generate_social_posts(client: genai.Client, store_name: str, topic: str, platform: str, tone: str, words: int, hashtags: bool) -> str:
    platform_specs = {
        "LinkedIn": "struttura: titolo accroccato + 3-5 bullet brevi + call-to-action finale. Stile professionale, ma umano.",
        "Instagram": "struttura: hook iniziale breve, corpo con 3-4 frasi, chiusura con CTA. Linguaggio semplice, emoticon moderate.",
        "X/Twitter": "struttura: singolo post conciso, massimo 40-60 parole, con hook e CTA breve.",
        "Facebook Page": "struttura: hook iniziale + corpo di 3-5 frasi con benefit chiari + CTA. Linguaggio accessibile.",
        "Facebook Group": "struttura: domanda iniziale o spunto per la community, 2-3 frasi di contesto, invito alla discussione. Stile conversazionale.",
    }
    tags_hint = "Includi 3-5 hashtag pertinenti alla fine." if hashtags else "Non inserire hashtag."
    prompt = (
        f"Sei un content strategist. Genera 2 varianti di post per {platform} "
        f"di circa {words} parole sul tema: {topic}. "
        f"Usa solo informazioni corrette dai documenti. "
        f"Adotta un tono {tone}. {platform_specs.get(platform, '')} {tags_hint} "
        "Evidenzia citazioni o dati rilevanti se presenti nei documenti. "
        "Formatta in modo leggibile per l'utente finale."
    )
    tool = Tool(file_search=FileSearch(file_search_store_names=[store_name]))
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config={"tools": [tool]},
    )
    return response.text if hasattr(response, "text") else str(response)


def generate_images_from_post(client: genai.Client, topic: str, tone: str, count: int = 2) -> list[str]:
    prompt = (
        f"Simple social media illustration for this topic: {topic}. "
        f"Tone: {tone}. Style: clean, readable, minimal text, flat colors."
    )
    images: list[str] = []
    try:
        result = client.models.generate_images(
            model=IMAGE_MODEL,
            prompt=prompt,
            config={"number_of_images": count},
        )
        # Try to extract base64 data from possible fields
        if hasattr(result, "generated_images") and result.generated_images:
            for gi in result.generated_images:
                img = getattr(gi, "image", None)
                if img and getattr(img, "image_bytes", None):
                    images.append(base64.b64encode(img.image_bytes).decode("utf-8"))
    except Exception as exc:
        st.warning(f"Impossibile generare immagini: {exc}")
    return images


def main() -> None:
    st.title("RAG locale con Gemini File Search")
    st.write("Carica documenti e fai domande senza uscire dal browser.")

    api_key_set = bool(os.environ.get("GEMINI_API_KEY"))
    if not api_key_set:
        st.error("Imposta GEMINI_API_KEY nell'ambiente prima di avviare l'app.")
        st.stop()

    client = get_client()
    if "store_name" not in st.session_state:
        st.session_state["store_name"] = get_or_create_store(client)
    store_name = st.session_state["store_name"]
    st.caption(f"Store in uso: {store_name}")

    with st.expander("Carica documento", expanded=True):
        if st.button("Crea nuovo store vuoto", help="Usa uno store nuovo per evitare risposte da documenti vecchi"):
            store_name = reset_store(client)
            st.caption(f"Store in uso: {store_name}")
        up_file = st.file_uploader("Scegli un file (PDF, DOCX, TXT, ecc.)", type=None)
        if up_file and st.button("Carica", type="primary"):
            upload_document(client, store_name, up_file)

    st.divider()

    st.subheader("Domande sui documenti")
    question = st.text_area("Domanda", placeholder="Scrivi qui la domanda...", height=100)
    if st.button("Chiedi", type="primary", disabled=not question.strip()):
        with st.spinner("Interrogo i documenti..."):
            try:
                answer = ask_question(client, store_name, question.strip())
                st.success("Risposta")
                st.write(answer)
            except Exception as exc:
                st.error(f"Errore: {exc}")

    st.divider()

    st.subheader("Generatore di post social (RAG)")
    topic = st.text_input("Tema o richiesta", placeholder="Es. riassumi il documento e crea un post")
    col1, col2, col3 = st.columns(3)
    with col1:
        platform = st.selectbox("Piattaforma", ["LinkedIn", "Instagram", "X/Twitter", "Facebook Page", "Facebook Group"])
    with col2:
        tone = st.selectbox("Tono", ["professionale", "informale", "ispirazionale", "tecnico"])
    with col3:
        words = st.slider("Lunghezza (parole circa)", 40, 200, 90, step=10)
    hashtags = st.checkbox("Aggiungi hashtag", value=True)
    gen_images = st.checkbox("Genera immagini", value=False)

    if st.button("Genera post", type="primary", disabled=not topic.strip()):
        with st.spinner("Genero i post..."):
            try:
                posts = generate_social_posts(client, store_name, topic.strip(), platform, tone, words, hashtags)
                st.success("Bozze generate")
                st.write(posts)
                if gen_images:
                    imgs = generate_images_from_post(client, topic.strip(), tone, count=2)
                    if imgs:
                        st.subheader("Immagini generate")
                        for b64 in imgs:
                            try:
                                st.image(base64.b64decode(b64))
                            except Exception:
                                pass
            except Exception as exc:
                st.error(f"Errore: {exc}")


if __name__ == "__main__":
    main()
