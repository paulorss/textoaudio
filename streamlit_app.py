# -*- coding: utf-8 -*-
import streamlit as st
import PyPDF2
import asyncio
from openai import AsyncOpenAI, OpenAIError # Import specific error
import io
import os
import re
import shutil

# --- Core Functions ---

def extract_text_from_pdf(file_path):
    """Extracts text from all pages of a PDF file."""
    try:
        with open(file_path, "rb") as file:
            pdf_reader = PyPDF2.PdfReader(file)
            text = ""
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text
            # Basic cleanup: remove excessive newlines/spaces
            text = re.sub(r'\s{2,}', ' ', text)
            text = re.sub(r'\n+', '\n', text).strip()
            return text
    except FileNotFoundError:
        st.error(f"Erro: O arquivo PDF '{os.path.basename(file_path)}' não foi encontrado.")
        return None
    except Exception as e:
        st.error(f"Erro ao extrair texto do PDF '{os.path.basename(file_path)}': {e}")
        return None

def split_text_into_articles(text):
    """Splits text into articles using regex based on 'Art. X'."""
    # Improved pattern to handle variations and potential leading/trailing spaces
    pattern = r"(Art\.\s*\d+º?\.?[\s\S]*?)(?=^\s*Art\.\s*\d+º?\.?|\Z)"
    # Use re.MULTILINE to make ^ match start of lines for lookahead
    articles_raw = re.findall(pattern, text, re.IGNORECASE | re.DOTALL | re.MULTILINE)
    clean_articles = []
    for article_text in articles_raw:
        article_text = article_text.strip()
        if article_text:
            # More robust extraction of article number
            article_num_match = re.match(r"Art\.\s*(\d+)", article_text, re.IGNORECASE)
            article_num = article_num_match.group(1) if article_num_match else "Desconhecido"
            # Further cleanup specific to article text if needed
            clean_article_text = re.sub(r'\s+', ' ', article_text).strip()
            clean_articles.append({"number": article_num, "text": clean_article_text})
    return clean_articles

async def generate_audio(input_text, voice, audio_format, openai_client):
    """Generates audio from text using OpenAI's TTS API asynchronously."""
    if not openai_client: # Should not happen if called correctly, but safe check
        return None, "Cliente OpenAI não inicializado."
    try:
        async with openai_client.audio.speech.with_streaming_response.create(
            model="tts-1", # Consider tts-1-hd for higher quality if needed
            voice=voice,
            input=input_text,
            response_format=audio_format
        ) as response:
            if response.status_code != 200:
                error_detail = await response.text()
                st.error(f"Erro da API OpenAI ({response.status_code}): {error_detail}")
                return None, f"API Error ({response.status_code})"
            audio_data = await response.read()
            return audio_data, None # Return audio data and no error
    except OpenAIError as e: # Catch specific OpenAI errors
        st.error(f"Erro da API OpenAI ao gerar áudio: {e}")
        return None, str(e)
    except Exception as e: # Catch other potential errors
        st.error(f"Erro inesperado ao chamar a API de geração de áudio: {e}")
        return None, str(e)

# --- Main Application Logic ---

def main():
    # Initialize session_state
    default_values = {
        'step': 'config', # Start at config step
        'api_key': '',
        'api_key_confirmed': False, # Track if user confirmed input
        'articles': [],
        'processed_articles': [],
        'selected_pdf': None
    }
    for key, value in default_values.items():
        if key not in st.session_state:
            st.session_state[key] = value

    st.title("Processador de PDF e Geração de Áudio Automático")

    # --- Callbacks ---
    def confirm_api_key():
        """Confirms the entered API key and updates state."""
        st.session_state.api_key = st.session_state.get('api_key_input', '')
        st.session_state.api_key_confirmed = bool(st.session_state.api_key) # True if key is not empty
        # No need to change step here, just confirm the key presence

    def start_processing_callback():
        """Checks conditions and moves to the processing step."""
        selected_pdf = st.session_state.get('selected_pdf')
        if selected_pdf:
            pdf_path = os.path.join("arquivos", selected_pdf)
            if os.path.exists(pdf_path):
                st.session_state.step = 'processing'
                st.rerun()
            else:
                 st.error(f"Arquivo PDF selecionado '{selected_pdf}' não encontrado. Verifique a pasta 'arquivos'.")
        else:
            st.warning("Por favor, selecione um arquivo PDF válido antes de continuar.")

    def reset_to_start():
        """Resets the application state."""
        keys_to_reset = ['step', 'articles', 'processed_articles', 'selected_pdf', 'api_key_confirmed']
        st.session_state.step = 'config' # Go back to config
        st.session_state.api_key = '' # Clear API key
        st.session_state.api_key_confirmed = False
        st.session_state.articles = []
        st.session_state.processed_articles = []
        st.session_state.selected_pdf = None

        # Clear widget states by removing them from session state if they exist
        for key in ['api_key_input', 'pdf_select', 'process_button', 'view_results_button', 'reset_button']:
             if key in st.session_state:
                 del st.session_state[key]
        # Clear download button states (more complex, might need prefix loop if keys are dynamic)
        # For simplicity, a full rerun often clears widgets effectively
        st.rerun()


    # --- UI Rendering ---

    # Step 1: Configuration (API Key Optional)
    if st.session_state.step == 'config':
        st.header("1. Chave API OpenAI (Opcional)")
        st.info("Forneça uma chave API da OpenAI para gerar novos áudios. Se deixar em branco, o app apenas verificará por áudios já existentes.")

        api_key_value = st.session_state.get('api_key_input', st.session_state.api_key)
        st.text_input(
            "Digite sua API Key da OpenAI (opcional)",
            type="password",
            key="api_key_input",
            value=api_key_value,
            on_change=confirm_api_key # Update confirmation status on change
        )

        # Display confirmation based on whether a key was entered *and confirmed*
        if st.session_state.api_key_confirmed:
             st.success("API Key fornecida. Novos áudios serão gerados se necessário.")
        else:
             # Check if the input field has content but hasn't triggered on_change yet
             if st.session_state.get('api_key_input'):
                  st.info("Pressione Enter ou clique fora para confirmar a chave API.")
             else:
                  st.warning("Nenhuma API Key fornecida. Apenas áudios existentes serão procurados.")


        # Proceed to PDF selection regardless of API key
        st.header("2. Selecionar Arquivo PDF")
        arquivos_dir = "arquivos"
        if not os.path.exists(arquivos_dir):
            try:
                os.makedirs(arquivos_dir)
                st.info(f"Pasta '{arquivos_dir}' criada. Adicione seus PDFs e atualize a página.")
            except OSError as e:
                st.error(f"Não foi possível criar a pasta '{arquivos_dir}': {e}")
                return # Stop if directory fails

        try:
            pdf_files = sorted([f for f in os.listdir(arquivos_dir) if f.lower().endswith(".pdf")])
        except Exception as e:
             st.error(f"Erro ao listar arquivos PDF em '{arquivos_dir}': {e}")
             pdf_files = []

        if not pdf_files:
            st.warning(f"Nenhum arquivo PDF encontrado na pasta '{arquivos_dir}'.")
        else:
            current_selection_index = None
            if st.session_state.selected_pdf in pdf_files:
                 current_selection_index = pdf_files.index(st.session_state.selected_pdf)

            selected_pdf_file = st.selectbox(
                "Escolha um arquivo PDF para processar:",
                pdf_files,
                key="pdf_select",
                index=current_selection_index,
                placeholder="Selecione um PDF..."
            )
            # Update state immediately if selection changes
            if selected_pdf_file != st.session_state.selected_pdf:
                st.session_state.selected_pdf = selected_pdf_file
                st.rerun() # Rerun to update display and potentially enable button

            if st.session_state.selected_pdf:
                 st.write(f"Arquivo selecionado: **{st.session_state.selected_pdf}**")
                 button_label = "Verificar Áudios Existentes"
                 if st.session_state.api_key_confirmed:
                      button_label = "Verificar e Gerar Áudios"
                 st.button(button_label, key="process_button", on_click=start_processing_callback)


    # Step 2: Processing
    elif st.session_state.step == 'processing':
        st.header("Processando PDF e Verificando/Gerando Áudios...")

        if not st.session_state.selected_pdf:
             st.error("Nenhum PDF selecionado.")
             reset_to_start()
             return

        pdf_path = os.path.join("arquivos", st.session_state.selected_pdf)
        pdf_name = os.path.splitext(st.session_state.selected_pdf)[0]
        output_folder = os.path.join("arquivos", pdf_name + "_audio")

        try:
            os.makedirs(output_folder, exist_ok=True) # Create if not exists, ignore if exists
        except OSError as e:
            st.error(f"Não foi possível criar/acessar a pasta de saída '{output_folder}': {e}")
            st.button("Voltar", on_click=reset_to_start)
            return

        # --- PDF Text Extraction ---
        with st.spinner("Extraindo texto do PDF..."):
            input_text = extract_text_from_pdf(pdf_path)
            if input_text is None: # Check for None explicitly after error handling in function
                st.error("Falha ao extrair texto do PDF. Verifique o arquivo e as permissões.")
                st.button("Voltar", on_click=reset_to_start)
                return
            st.success("Texto extraído com sucesso.")

        # --- Text Splitting ---
        with st.spinner("Dividindo o texto em artigos..."):
            articles = split_text_into_articles(input_text)
            if not articles:
                st.warning("Nenhum artigo 'Art. X' encontrado. Verificando/gerando áudio para o texto completo.")
                articles = [{"number": "Completo", "text": input_text}]
            else:
                 st.success(f"{len(articles)} artigos encontrados.")
            st.session_state.articles = articles

        # --- Audio Generation / Verification ---
        max_articles_to_process = min(10, len(articles)) # Limit processing
        st.subheader(f"Verificando/Gerando Áudios (até {max_articles_to_process} artigos)")

        # Initialize OpenAI client ONLY if API key is provided and confirmed
        openai_client = None
        if st.session_state.api_key_confirmed and st.session_state.api_key:
            try:
                openai_client = AsyncOpenAI(api_key=st.session_state.api_key)
                st.info("Cliente OpenAI inicializado. Tentará gerar novos áudios.")
            except Exception as e:
                 st.error(f"Erro ao inicializar o cliente OpenAI com a chave fornecida: {e}. Apenas áudios existentes serão verificados.")
                 # Proceed without the client
        else:
             st.info("Nenhuma chave API válida fornecida. Apenas áudios existentes serão verificados.")


        voice = "alloy" # Default voice
        audio_format = "mp3"
        progress_bar = st.progress(0)
        progress_text_area = st.empty()
        st.session_state.processed_articles = [] # Reset list

        async def process_article(article_data, index, total_articles, client):
            """Processes a single article: checks existence, generates if client available, saves."""
            article_num = article_data["number"]
            text_for_audio = article_data["text"]
            current_progress_val = (index + 1) / total_articles

            safe_article_num = re.sub(r'\W+', '_', str(article_num))
            file_name = f"artigo_{safe_article_num}.{audio_format}"
            file_path = os.path.join(output_folder, file_name)

            result = {"number": article_num, "success": False, "path": None, "status": "Pending", "error": None}

            # 1. Check if audio file already exists
            if os.path.exists(file_path):
                progress_text_area.text(f"🔄 Artigo '{article_num}' ({index+1}/{total_articles}): Áudio já existe.")
                result.update({"success": True, "path": file_path, "status": "Exists"})
            # 2. If file doesn't exist, check if we can generate (API key provided?)
            elif client:
                progress_text_area.text(f"⏳ Gerando áudio para Artigo '{article_num}' ({index+1}/{total_articles})...")
                max_chars = 4096
                if len(text_for_audio) > max_chars:
                    st.warning(f"Artigo {article_num} truncado para {max_chars} caracteres.")
                    text_for_audio = text_for_audio[:max_chars]

                audio_data, api_error = await generate_audio(text_for_audio, voice, audio_format, client)

                if audio_data:
                    try:
                        with open(file_path, "wb") as audio_file:
                            audio_file.write(audio_data)
                        result.update({"success": True, "path": file_path, "status": "Generated"})
                    except IOError as e:
                        save_error_msg = f"Erro ao salvar áudio: {e}"
                        st.error(save_error_msg)
                        result.update({"success": False, "status": "Failed", "error": save_error_msg})
                else:
                    result.update({"success": False, "status": "Failed", "error": api_error or "Falha na geração."})
            # 3. File doesn't exist and no API key/client
            else:
                progress_text_area.text(f"⚠️ Artigo '{article_num}' ({index+1}/{total_articles}): Áudio não encontrado e API Key não fornecida.")
                result.update({"success": False, "status": "Skipped - No API Key", "error": "Áudio não existente e API Key não fornecida."})

            progress_bar.progress(current_progress_val)
            return result

        # Run async tasks
        async def run_tasks():
             # Pass the potentially None openai_client to each task
             tasks = [process_article(articles[i], i, max_articles_to_process, openai_client)
                      for i in range(max_articles_to_process)]
             results = await asyncio.gather(*tasks, return_exceptions=True)

             final_results = []
             for i, res in enumerate(results):
                 if isinstance(res, Exception):
                     article_num = articles[i]['number']
                     st.error(f"Erro inesperado no processamento do Artigo {article_num}: {res}")
                     final_results.append({
                         "number": article_num, "success": False, "path": None,
                         "status": "Failed", "error": f"Erro inesperado: {res}"
                     })
                 else:
                     final_results.append(res)
             st.session_state.processed_articles = final_results

        # Execute processing
        try:
             asyncio.run(run_tasks())
        except Exception as e:
             st.error(f"Ocorreu um erro crítico durante o processamento: {e}")

        # --- Finalization ---
        progress_bar.progress(1.0)
        processed_count = len(st.session_state.processed_articles)
        # Success here means audio is available (either existed or was generated)
        success_count = sum(1 for item in st.session_state.processed_articles if item.get("success"))
        progress_text_area.success(f"Processamento concluído! {success_count}/{processed_count} artigos com áudio disponível/verificado.")
        st.info(f"Arquivos de áudio estão na pasta: {output_folder}")
        st.session_state.step = 'results'
        if st.button("Ver Resultados", key="view_results_button"):
            st.rerun()

    # Step 3: Results
    elif st.session_state.step == 'results':
        st.header("Resultados do Processamento")

        if not st.session_state.selected_pdf:
             st.warning("Informação do PDF não encontrada.")
             reset_to_start()
             return

        pdf_name = os.path.splitext(st.session_state.selected_pdf)[0]
        output_folder = os.path.join("arquivos", pdf_name + "_audio")

        st.subheader(f"PDF Processado: {st.session_state.selected_pdf}")
        st.write(f"Pasta de saída dos áudios: `{output_folder}`")

        if not st.session_state.processed_articles:
            st.warning("Nenhum artigo foi processado ou verificado.")
        else:
            # Display Statistics
            total_attempted = len(st.session_state.processed_articles)
            # Success = Exists or Generated
            successful_items = [item for item in st.session_state.processed_articles if item.get("success")]
            successful_count = len(successful_items)
            generated_count = sum(1 for item in successful_items if item.get("status") == "Generated")
            existing_count = sum(1 for item in successful_items if item.get("status") == "Exists")
            # Skipped = No API key and file not found
            skipped_count = sum(1 for item in st.session_state.processed_articles if item.get("status") == "Skipped - No API Key")
            # Failed = Attempted generation but failed
            failed_count = sum(1 for item in st.session_state.processed_articles if item.get("status") == "Failed")


            st.metric("Total Verificado/Processado", f"{total_attempted}")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Áudio Disponível ✅", f"{successful_count} ({existing_count} Existentes + {generated_count} Gerados)")
            # col2.metric("Gerados Nesta Sessão", f"{generated_count}")
            # col3.metric("Existentes", f"{existing_count}")
            col2.metric("Pulados (Sem Chave API) ⚠️", f"{skipped_count}")
            col3.metric("Falhas na Geração ❌", f"{failed_count}")


            # List Processed Articles
            st.subheader("Detalhes por Artigo:")
            for index, item in enumerate(st.session_state.processed_articles):
                article_num = item.get("number", "N/A")
                status = item.get("status", "Desconhecido")
                status_emoji = "❓"
                status_text = status

                if status == "Exists":
                    status_emoji = "🔄"
                    status_text = "Existente (encontrado)"
                elif status == "Generated":
                    status_emoji = "✅"
                    status_text = "Gerado nesta sessão"
                elif status == "Skipped - No API Key":
                     status_emoji = "⚠️"
                     status_text = "Pulado (sem chave API)"
                elif status == "Failed":
                    status_emoji = "❌"
                    status_text = "Falhou"

                st.markdown(f"---")
                # Display status prominently
                st.write(f"{status_emoji} **Artigo {article_num}**")
                st.caption(f"Status: {status_text}")


                # Show audio player and download if successful (Exists or Generated)
                if item.get("success") and item.get("path") and os.path.exists(item["path"]):
                    try:
                        with open(item["path"], "rb") as audio_file:
                            audio_bytes = audio_file.read()
                        st.audio(audio_bytes, format="audio/mp3")
                        file_name = os.path.basename(item["path"])
                        #st.download_button(
                        #    label=f"Baixar (Art. {article_num})",
                        #    data=audio_bytes,
                        #    file_name=file_name,
                        #    mime="audio/mp3",
                        #    key=f"download_button_{index}_{article_num}" # Unique key
                        #)
                    except FileNotFoundError:
                         st.error(f"Arquivo de áudio não encontrado em '{item['path']}'.")
                    except Exception as e:
                         st.error(f"Erro ao carregar/exibir áudio: {e}")
                # Show error message if failed or skipped
                elif not item.get("success"):
                    error_msg = item.get("error", "Detalhe não disponível.")
                    if status == "Skipped - No API Key":
                         st.info(f"Motivo: {error_msg}") # Use info for skipped
                    else: # Failed status
                         st.error(f"Detalhe da falha: {error_msg}")

        # Button to go back to the start
        st.button("Processar outro PDF / Voltar", on_click=reset_to_start, key="reset_button")

# --- Sidebar ---
st.sidebar.warning("⚠️ **Aviso:** Lembre-se de informar aos usuários finais se o áudio foi gerado por Inteligência Artificial (IA).")
st.sidebar.info("App para converter artigos de PDFs em áudio, com ou sem API Key da OpenAI.")

# --- Entry Point ---
if __name__ == "__main__":
    main()
