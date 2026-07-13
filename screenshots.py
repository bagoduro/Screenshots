import asyncio
import csv
import argparse
import time
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

# ====================== CONFIGURAÇÕES ======================
MAX_CONCURRENT = 30
BATCH_SIZE = 50
TIMEOUT_PLAYWRIGHT = 15000   # 15 segundos (aumentei um pouco)
PORTA_PADRAO = "80"
CHROMIUM_PATH = "/usr/bin/chromium-browser"
PASTA_BASE = "execucoes"

semaphore = asyncio.Semaphore(MAX_CONCURRENT)

async def capturar_tela(ip: str, porta: str, browser, pasta_destino: Path):
    url = f"http://{ip}:{porta}"
    nome_arquivo = f"{ip}_{porta}.png"
    caminho = pasta_destino / nome_arquivo

    if caminho.exists():
        return {"ip": ip, "porta": porta, "status": "Pulado", "motivo": "Já existe", "arquivo": str(caminho)}

    try:
        # Cria um novo contexto com opções para ignorar certificados
        context = await browser.new_context(
            ignore_https_errors=True,  # <--- IGNORA ERROS DE CERTIFICADO
            bypass_csp=True            # opcional, ajuda em alguns casos
        )
        page = await context.new_page()
        await page.set_viewport_size({"width": 1280, "height": 720})

        # Navega com opção de ignorar redirecionamentos forçados
        await page.goto(url, timeout=TIMEOUT_PLAYWRIGHT, wait_until="domcontentloaded")
        
        # Verifica se apareceu a tela de "Your connection is not private"
        # Se aparecer, clica em "Advanced" e depois "Proceed"
        try:
            # Espera um pouco para a página carregar
            await asyncio.sleep(1)
            
            # Verifica se o título contém "not private" ou "certificate"
            titulo = await page.title()
            if "not private" in titulo.lower() or "certificate" in titulo.lower():
                # Clica em "Advanced" se existir
                advanced_btn = await page.query_selector('text=Advanced')
                if advanced_btn:
                    await advanced_btn.click()
                    await asyncio.sleep(0.5)
                    
                    # Clica em "Proceed" ou "Continue"
                    proceed_btn = await page.query_selector('text=Proceed')
                    if not proceed_btn:
                        proceed_btn = await page.query_selector('text=Continue')
                    if proceed_btn:
                        await proceed_btn.click()
                        await asyncio.sleep(1)  # espera a página carregar
        except Exception:
            pass  # Se não tiver botão, segue em frente

        # Tira o screenshot
        await page.screenshot(path=caminho, full_page=False)
        await page.close()
        await context.close()

        return {"ip": ip, "porta": porta, "status": "Sucesso", "motivo": "HTTP", "arquivo": str(caminho)}

    except Exception as e:
        return {"ip": ip, "porta": porta, "status": "Falha", "motivo": str(e)[:80], "arquivo": ""}

async def processar_ip(ip: str, porta: str, browser, pasta_destino: Path):
    async with semaphore:
        return await capturar_tela(ip, porta, browser, pasta_destino)

async def main():
    parser = argparse.ArgumentParser(description="Captura screenshots de páginas HTTP")
    parser.add_argument("-f", "--file", default="ips.txt", help="Arquivo com a lista de IPs (um por linha)")
    parser.add_argument("-p", "--porta", default=PORTA_PADRAO, help="Porta HTTP (padrão: 80)")
    args = parser.parse_args()

    arquivo_ips = Path(args.file)
    porta = args.porta

    if not arquivo_ips.exists():
        print(f"❌ Arquivo '{args.file}' não encontrado!")
        return

    with open(arquivo_ips, "r", encoding="utf-8") as f:
        ips = [linha.strip() for linha in f if linha.strip() and not linha.startswith("#")]

    if not ips:
        print("❌ Nenhum IP válido.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pasta_execucao = Path(PASTA_BASE) / f"execucao_{timestamp}"
    pasta_execucao.mkdir(parents=True, exist_ok=True)

    print(f"📁 Resultados serão salvos em: {pasta_execucao}/")
    print(f"🚀 Capturando {len(ips)} IPs do arquivo '{args.file}' na porta {porta}")
    print(f"Concorrência: {MAX_CONCURRENT} | Lotes: {BATCH_SIZE}\n")

    resultados = []
    success_count = 0
    start_time = time.time()

    async with async_playwright() as p:
        # Lança o navegador com argumentos extras para ignorar certificados
        browser = await p.chromium.launch(
            headless=True,
            executable_path=CHROMIUM_PATH,
            args=[
                '--ignore-certificate-errors',
                '--ignore-ssl-errors',
                '--disable-web-security'
            ]
        )

        for i in range(0, len(ips), BATCH_SIZE):
            lote = ips[i:i+BATCH_SIZE]
            print(f"📸 Lote {i//BATCH_SIZE + 1} ({len(lote)} IPs)...")

            tarefas = [processar_ip(ip, porta, browser, pasta_execucao) for ip in lote]
            batch_results = await asyncio.gather(*tarefas, return_exceptions=True)

            for res in batch_results:
                if isinstance(res, dict):
                    resultados.append(res)
                    if res["status"] == "Sucesso":
                        success_count += 1
                else:
                    ip_atual = lote[len(resultados) % len(lote)]
                    resultados.append({
                        "ip": ip_atual,
                        "porta": porta,
                        "status": "Falha",
                        "motivo": f"Erro: {str(res)[:80]}",
                        "arquivo": ""
                    })

            print(f"   ✅ Sucessos: {success_count} | Processados: {len(resultados)}/{len(ips)}\n")
            await asyncio.sleep(0.1)

        await browser.close()

    csv_file = pasta_execucao / f"relatorio_{timestamp}.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["IP", "Porta", "Status", "Motivo", "Arquivo"])
        for r in resultados:
            writer.writerow([r["ip"], r["porta"], r["status"], r["motivo"], r["arquivo"]])

    duracao = time.time() - start_time
    print(f"\n✅ Concluído em {duracao/60:.1f} min")
    print(f"   Capturas: {success_count} ({success_count/len(ips)*100:.1f}%)")
    print(f"📁 Todos os resultados em: {pasta_execucao}/")

if __name__ == "__main__":
    asyncio.run(main())
