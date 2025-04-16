# -*- coding: utf-8 -*-
import streamlit as st
import PyPDF2 # Importar PyPDF2
import asyncio
from openai import AsyncOpenAI, OpenAIError
import io     # Importar io
import os
import re
import base64

# Tenta importar o componente PDF viewer
try:
    from streamlit_pdf_viewer import pdf_viewer
except ImportError:
    st.error("Por favor, instale a biblioteca 'streamlit-pdf-viewer': pip install streamlit-pdf-viewer")
    st.stop()

# --- Core Functions ---

# Função para extrair texto com PyPDF2
def extract_text_from_pdf(pdf_bytes):
    """Extrai texto de um objeto de bytes PDF."""
    text = ""
    try:
        pdf_file = io.BytesIO(pdf_bytes)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n\n" # Adiciona espaço entre páginas
        # Limpeza básica
        text = re.sub(r'\s{3,}', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()
    except Exception as e:
        st.error(f"Erro ao extrair texto do PDF com PyPDF2: {e}")
        return None # Retorna None em caso de erro na extração

async def generate_audio(input_text, voice, audio_format, openai_client):
    """Gera áudio do texto usando a API TTS do OpenAI de forma assíncrona."""
    if not openai_client:
        st.error("Erro: Cliente OpenAI não inicializado. Verifique a chave API.")
        return None, "Cliente OpenAI não inicializado."
    if not input_text or not input_text.strip():
        st.warning("Nenhum texto fornecido (colado) para gerar áudio.")
        return None, "Texto vazio."
    try:
        max_chars = 4096
        if len(input_text) > max_chars:
            st.warning(f"Texto truncado para {max_chars} caracteres para a API TTS.")
            input_text = input_text[:max_chars]
        async with openai_client.audio.speech.with_streaming_response.create(
            model="tts-1", voice=voice, input=input_text, response_format=audio_format
        ) as response:
            if response.status_code != 200:
                error_detail = await response.text()
                st.error(f"Erro da API OpenAI ({response.status_code}): {error_detail}")
                return None, f"API Error ({response.status_code})"
            audio_data = await response.read()
            return audio_data, None
    except OpenAIError as e:
        st.error(f"Erro da API OpenAI ao gerar áudio: {e}")
        return None, str(e)
    except Exception as e:
        st.error(f"Erro inesperado ao chamar a API de geração de áudio: {e}")
        return None, str(e)

# --- Main Application Logic ---

def main():
    # Initialize session_state
    default_values = {
        'api_key': '',
        'api_key_confirmed': False,
        'selected_pdf_name': None,
        'pdf_bytes': None,
        'extracted_text': None,
        'text_to_speak_pasted': '',
        'generated_audio_bytes': None,
        'output_folder': None
    }
    for key, value in default_values.items():
        if key not in st.session_state:
            st.session_state[key] = value

    st.title("Leitor de PDF com Geração de Áudio por Seleção (Copiar/Colar)")
    st.info("Instruções: Carregue um PDF -> Selecione texto no visualizador OU no texto extraído -> Copie (Ctrl+C) -> Cole na área da Etapa 4 (Ctrl+V) -> Gere o áudio.")

    # --- Callbacks ---
    def confirm_api_key():
        st.session_state.api_key = st.session_state.get('api_key_input', '')
        st.session_state.api_key_confirmed = bool(st.session_state.api_key)

    def load_pdf_and_extract_text():
        """Carrega o PDF, extrai o texto e atualiza o estado."""
        uploaded_file = st.session_state.get('pdf_uploader')
        # Limpar estados anteriores ao carregar novo arquivo ou limpar seleção
        st.session_state.pdf_bytes = None
        st.session_state.extracted_text = None
        st.session_state.generated_audio_bytes = None
        st.session_state.text_to_speak_pasted = ""
        st.session_state.selected_pdf_name = None
        st.session_state.output_folder = None

        if uploaded_file:
            pdf_name = os.path.splitext(uploaded_file.name)[0]
            st.session_state.selected_pdf_name = uploaded_file.name
            st.session_state.pdf_bytes = uploaded_file.read() # Lê os bytes

            # -- Extrai o texto AQUI --
            with st.spinner("Extraindo texto do PDF..."):
                st.session_state.extracted_text = extract_text_from_pdf(st.session_state.pdf_bytes)
                if st.session_state.extracted_text is None:
                    st.warning("Não foi possível extrair o texto do PDF para exibição separada, mas a visualização ainda pode funcionar.")
            # -------------------------

            # Cria pasta de saída
            pdf_folder = "arquivos"
            output_folder = os.path.join(pdf_folder, pdf_name + "_audio_copiado")
            try:
                os.makedirs(output_folder, exist_ok=True)
                st.session_state.output_folder = output_folder
            except OSError as e:
                st.error(f"Não foi possível criar a pasta de saída '{output_folder}': {e}")
                st.session_state.output_folder = None

    async def generate_audio_for_pasted_text():
        text_pasted = st.session_state.get('text_to_speak_input', '')
        st.session_state.text_to_speak_pasted = text_pasted
        if not text_pasted or not text_pasted.strip():
            st.warning("Por favor, cole o texto selecionado na área abaixo antes de gerar o áudio.")
            return
        if not st.session_state.api_key_confirmed:
            st.error("É necessária uma chave API da OpenAI para gerar áudio.")
            return
        openai_client = None
        try:
            openai_client = AsyncOpenAI(api_key=st.session_state.api_key)
        except Exception as e:
            st.error(f"Erro ao inicializar o cliente OpenAI: {e}")
            return
        voice = "alloy"
        audio_format = "mp3"
        with st.spinner("Gerando áudio para o texto colado..."):
            audio_data, error = await generate_audio(text_pasted, voice, audio_format, openai_client)
            if audio_data:
                st.session_state.generated_audio_bytes = audio_data
                st.success("Áudio gerado com sucesso!")
                if st.session_state.output_folder:
                     try:
                        safe_text_prefix = re.sub(r'\W+', '_', text_pasted[:30].strip())
                        if not safe_text_prefix: safe_text_prefix = "audio_colado"
                        output_filename = f"{safe_text_prefix}_{len(text_pasted)}.{audio_format}"
                        output_path = os.path.join(st.session_state.output_folder, output_filename)
                        with open(output_path, "wb") as f:
                            f.write(audio_data)
                        st.info(f"Áudio salvo em: {output_path}")
                     except Exception as e:
                         st.error(f"Erro ao salvar o arquivo de áudio: {e}")
            else:
                st.session_state.generated_audio_bytes = None
                st.error(f"Falha ao gerar áudio. {error or ''}")

    # --- UI Rendering ---

    # 1. API Key Input
    st.header("1. Chave API OpenAI (Obrigatória)")
    api_key_value = st.session_state.get('api_key_input', st.session_state.api_key)
    st.text_input(
        "Digite sua API Key da OpenAI", type="password", key="api_key_input",
        value=api_key_value, on_change=confirm_api_key,
        help="Sua chave não é armazenada permanentemente, apenas durante a sessão."
    )
    if st.session_state.api_key_confirmed:
        st.success("API Key fornecida.")
    else:
        st.warning("API Key é necessária para a funcionalidade de geração de áudio.")

    st.divider()

    # 2. PDF Upload
    st.header("2. Carregar Arquivo PDF")
    uploaded_file = st.file_uploader(
        "Escolha um arquivo PDF", type="pdf", key="pdf_uploader",
        on_change=load_pdf_and_extract_text
    )

    st.divider()

    # 3. PDF Viewer E Texto Extraído
    if st.session_state.pdf_bytes: # Verifica se um PDF foi carregado
        st.header("3. Visualizar PDF e Texto Extraído")
        st.info("Use o mouse para selecionar e copiar (Ctrl+C) o texto desejado do visualizador abaixo OU da área de texto extraído.")

        # 3a. Visualizador de PDF
        st.subheader("Visualizador Interativo do PDF")
        try:
            with st.container(height=400, border=True):
                 pdf_viewer(input=st.session_state.pdf_bytes, width=700)
        except Exception as e:
             st.error(f"Erro ao exibir o PDF: {e}")
             st.warning("Verifique se o arquivo PDF não está corrompido.")

        st.markdown("---") # Separador

        # 3b. Texto Extraído (se disponível)
        st.subheader("Texto Extraído (para facilitar a cópia)")
        if st.session_state.extracted_text:
            st.text_area(
                "Texto completo extraído do PDF:",
                value=st.session_state.extracted_text,
                height=250,
                key="extracted_text_display",
                disabled=True, # CORRIGIDO: Removido 'read_only=True'
                help="Este texto foi extraído automaticamente. Você pode selecionar e copiar daqui."
            )
        else:
            st.info("Texto não pôde ser extraído ou não há texto no PDF.")

        st.divider() # Separador antes da próxima seção

        # 4. Colar Texto e Gerar Áudio
        st.header("4. Colar Texto Selecionado e Gerar Áudio")
        st.info("Cole o texto copiado (Ctrl+V) na área abaixo e clique em 'Gerar Áudio'.")

        st.text_area(
            "Texto selecionado para converter em áudio:",
            key="text_to_speak_input",
            height=150,
            placeholder="Cole o texto que você copiou (do visualizador ou do texto extraído) aqui..."
        )

        if st.button("Gerar Áudio do Texto Colado Acima", disabled=not st.session_state.api_key_confirmed):
            asyncio.run(generate_audio_for_pasted_text())
            st.rerun()

        # Exibir player de áudio
        if st.session_state.generated_audio_bytes:
            st.subheader("Áudio Gerado:")
            st.audio(st.session_state.generated_audio_bytes, format="audio/mp3")

    elif uploaded_file is None:
         st.info("Aguardando o carregamento de um arquivo PDF...")
    elif st.session_state.extracted_text is None and st.session_state.pdf_bytes is not None:
         # Caso onde o carregamento ocorreu mas a extração falhou (já tratado na extração)
         st.warning("O PDF foi carregado, mas não foi possível extrair o texto para exibição separada.")




# --- Entry Point ---
if __name__ == "__main__":
    #st.set_page_config(layout="wide")
    main()
