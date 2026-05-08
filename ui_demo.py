import time
import random
import math
import json
import urllib.request
import urllib.error
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.console import Console
from rich.text import Text
import plotext as plt

MAX_EPOCHS = 150  # Reduziert, damit die Demo schnell durchläuft

class PlotextRenderable:
    def __init__(self, data1: list, name1: str, color1: str, 
                 data2: list = None, name2: str = "", color2: str = "", 
                 title: str = ""):
        self.data1 = data1
        self.name1 = name1
        self.color1 = color1
        self.data2 = data2
        self.name2 = name2
        self.color2 = color2
        self.title = title

    def __rich_console__(self, console, options):
        width = options.max_width
        height = options.max_height

        plt.clf()
        plt.plotsize(width, height)
        
        plt.plot(self.data1, marker="braille", color=self.color1, label=self.name1)
        if self.data2:
            plt.plot(self.data2, marker="braille", color=self.color2, label=self.name2)
            
        plt.title(self.title)
        plt.theme("clear")
        plt.xaxes(1, 0)
        plt.yaxes(1, 0)

        ansi_string = plt.build()
        yield Text.from_ansi(ansi_string)

def make_layout() -> Layout:
    layout = Layout(name="root")
    layout.split(
        Layout(name="header", size=3),
        Layout(name="main", ratio=1),
        Layout(name="footer", size=3)
    )
    layout["main"].split_row(
        Layout(name="left_panel", ratio=2),
        Layout(name="right_panel", ratio=5)
    )
    layout["left_panel"].split_column(
        Layout(name="metrics", ratio=2),
        Layout(name="system_stats", ratio=1)
    )
    layout["right_panel"].split_column(
        Layout(name="top_graphs", ratio=1),
        Layout(name="bottom_graphs", ratio=1)
    )
    layout["top_graphs"].split_row(
        Layout(name="graph_equity", ratio=1),
        Layout(name="graph_acc", ratio=1)
    )
    layout["bottom_graphs"].split_row(
        Layout(name="graph_loss", ratio=1),
        Layout(name="graph_conf", ratio=1)
    )
    return layout

def get_metrics_table(epoch: int, val_loss: float, accuracy: float, reward: float) -> Table:
    table = Table(title="Live Metriken", expand=True)
    table.add_column("Metrik", style="cyan")
    table.add_column("Wert", justify="right", style="magenta")
    loss_color = "green" if val_loss < 0.2 else "yellow"
    acc_color = "green" if accuracy > 0.6 else "yellow"
    table.add_row("Aktuelle Epoche", f"{epoch} / {MAX_EPOCHS}")
    table.add_row("Val Loss", f"[{loss_color}]{val_loss:.4f}[/{loss_color}]")
    table.add_row("Win Rate", f"[{acc_color}]{accuracy*100:.1f}%[/{acc_color}]")
    table.add_row("Avg Reward", f"{reward:.2f}")
    table.add_row("Drawdown", f"-{random.uniform(1.0, 3.5):.1f}%")
    table.add_row("Trades/Batch", f"{random.randint(40, 60)}")
    return table

import os

def get_llm_analysis(stats: dict) -> str:
    """Fragt die kostenlose Google Gemini API (Gemini 1.5 Flash) nach einer Experten-Meinung."""
    
    # Hier muss dein kostenloser API Key rein!
    # Du bekommst ihn kostenlos auf: https://aistudio.google.com/app/apikey
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "DEIN_API_KEY_HIER_EINFUEGEN")
    
    if GEMINI_API_KEY == "DEIN_API_KEY_HIER_EINFUEGEN":
        return "[yellow]⚠️ API Key fehlt![/yellow]\nHol dir einen [bold]völlig kostenlosen[/bold] Key auf [cyan]https://aistudio.google.com/app/apikey[/cyan] und trage ihn im Code ein.\nDann analysiert Google's stärkstes KI-Modell dein Trading in Sekundenschnelle!"

    prompt = f"""
Du bist ein Trading-KI Experte. Analysiere folgende Trainings-Metriken eines Trading-Bots und gib eine kurze, prägnante Empfehlung (max 4 Sätze) auf Deutsch.
- Epochen: {stats.get('epochs')}
- Win Rate: {stats.get('final_acc', 0)*100:.1f}% (Best: {stats.get('best_acc', 0)*100:.1f}%)
- Val Loss: {stats.get('final_loss', 0):.4f} (Best: {stats.get('min_loss', 0):.4f})
- Equity: Start 1000$, Ende ${stats.get('final_eq', 1000):.2f} (Peak: ${stats.get('best_eq', 1000):.2f})

Nenne eine Stärke, eine Schwäche und eine konkrete technische Empfehlung. Keine Formatierungen wie Fett/Kursiv.
"""
    
    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.5,
            "maxOutputTokens": 150
        }
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    try:
        req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        return f"[red]Fehler bei der Verbindung zu Google Gemini: {e}[/red]"

def show_summary(console: Console, stats: dict):
    """Löscht das Terminal und zeigt eine extrem detaillierte Auswertung."""
    console.clear()
    
    title = Panel("[bold gold1]🚀 TRAINING ABGESCHLOSSEN - AUSFÜHRLICHER REPORT[/bold gold1]", style="white on dark_blue")
    console.print(title, justify="center")
    console.print()
    
    table = Table(show_header=True, header_style="bold magenta", expand=True, border_style="gold1")
    table.add_column("Metrik", style="cyan", ratio=1)
    table.add_column("Letzter Wert", justify="right", style="white", ratio=1)
    table.add_column("Bestwert (Peak)", justify="right", style="green", ratio=1)
    table.add_column("Bewertung", justify="center", ratio=1)
    
    ep = stats.get("epochs", 0)
    dur = stats.get("duration", 0.001)
    
    # Metriken für die Tabelle extrahieren
    feq = stats.get("final_eq", 1000)
    beq = stats.get("best_eq", 1000)
    table.add_row("Portfolio Equity", f"${feq:.2f}", f"${beq:.2f}", "[green]✅ Profitabel[/green]" if feq > 1000 else "[red]❌ Verlust[/red]")
    
    facc = stats.get("final_acc", 0)
    bacc = stats.get("best_acc", 0)
    table.add_row("Win Rate / Acc", f"{facc*100:.2f}%", f"{bacc*100:.2f}%", "[green]✅ Solide[/green]" if facc > 0.55 else "[yellow]⚠️ Verbessern[/yellow]")
    
    floss = stats.get("final_loss", 0)
    mloss = stats.get("min_loss", 0)
    table.add_row("Validation Loss", f"{floss:.4f}", f"{mloss:.4f}", "[green]✅ Konvergiert[/green]" if floss < 1.0 else "[yellow]⚠️ Underfitting[/yellow]")
    
    console.print(table)
    console.print()
    
    # --- Detaillierte KI-Auswertung generieren ---
    
    # 1. Stärken analysieren
    good_points = []
    if facc > 0.55:
        good_points.append(f"[green]✓ Win-Rate ({facc*100:.1f}%):[/green] Das Modell gewinnt mehr Trades als es verliert. Ab >55% ist der statistische Vorteil (Edge) stark genug für Live-Trading.")
    if feq > 1050:
        good_points.append(f"[green]✓ Profitabilität (+${feq - 1000:.2f}):[/green] Die Equity-Kurve zeigt einen klaren Aufwärtstrend. Das Risk-Reward-Verhältnis scheint gesund zu sein.")
    if mloss < 0.2:
        good_points.append(f"[green]✓ Feature-Konvergenz:[/green] Der Loss fiel sehr schnell auf {mloss:.4f}. Die Features (z.B. Yields, MACD) haben hohe Vorhersagekraft.")
    if not good_points:
        good_points.append("[dim]Bisher keine klaren Stärken erkennbar. Das Modell lernt noch nicht das richtige Signal.[/dim]")

    # 2. Schwächen analysieren
    bad_points = []
    if facc < 0.50:
        bad_points.append(f"[red]✗ Win-Rate zu niedrig ({facc*100:.1f}%):[/red] Das Modell performt schlechter als ein Münzwurf. Überprüfe die Labels (Y-Daten) oder Feature-Skalierung.")
    if (beq - feq) / beq > 0.05: # Mehr als 5% Drawdown vom Peak
        bad_points.append(f"[red]✗ Hoher Drawdown ({((beq - feq) / beq)*100:.1f}%):[/red] Das System baut schnelle Profite auf, verliert sie aber in wenigen Trades wieder. Stop-Losses sind zu weit gefasst.")
    if floss > mloss * 1.5: # Val-Loss steigt wieder an
        bad_points.append(f"[red]✗ Starkes Overfitting:[/red] Der Validation Loss ({floss:.4f}) ist viel höher als der Bestwert ({mloss:.4f}). Das Modell merkt sich die Trainingsdaten auswendig.")
    if not bad_points:
        bad_points.append("[green]Keine kritischen Schwächen gefunden. Das Setup ist sehr stabil![/green]")

    # 3. Nächste Schritte
    next_steps = ""
    if floss > mloss * 1.5:
        next_steps = "• [b]Overfitting bekämpfen:[/b] Erhöhe Dropout (z.B. auf 0.3), nutze L2-Regularisierung (Weight Decay) oder reduziere die Modellgröße (weniger Neuronen).\n• [b]Early Stopping:[/b] Beende das Training, sobald der Val-Loss ansteigt."
    elif facc < 0.52:
        next_steps = "• [b]Feature Engineering:[/b] Das Modell findet keine Muster. Füge neue Features (Orderbuch-Tiefe, stärkere gleitende Durchschnitte) hinzu.\n• [b]Balancing:[/b] Überprüfe, ob im Datensatz mehr 'Buy' als 'Sell' Signale sind (Class Imbalance)."
    elif feq < 1000:
        next_steps = "• [b]Risk Management:[/b] Das Modell hat eine gute Win-Rate, verliert aber Geld. Der Take-Profit muss größer sein als der Stop-Loss (Risk:Reward > 1:1.5)."
    else:
        next_steps = "• [b]Bereit für Paper-Trading:[/b] Die Metriken sind exzellent. Speichere das Modell und teste es auf Forward-Test-Daten (Live Paper-Trading), um Slippage und Spread zu evaluieren."

    details = f"""[b]⏱️ System-Laufzeit:[/b]
Absolvierte Epochen: [cyan]{ep} / {MAX_EPOCHS}[/cyan] ({ep/MAX_EPOCHS*100:.1f}%) in [cyan]{dur:.1f}s[/cyan] ({ep/dur:.1f} Epochen/s)

[b]⭐ Was gut funktioniert (Stärken):[/b]
{chr(10).join(good_points)}

[b]⚠️ Was verbessert werden muss (Schwächen):[/b]
{chr(10).join(bad_points)}

[b]🎯 Strategische Empfehlung (Next Steps):[/b]
{next_steps}"""
    
    console.print(Panel(details, title="🧠 Logik-Analyst & Diagnose-Report", border_style="blue"))
    console.print()

    # --- LLM API CALL ---
    with console.status("[bold cyan]Warte auf LLM (Ollama) Auswertung...[/bold cyan]", spinner="dots"):
        llm_response = get_llm_analysis(stats)
        
    console.print(Panel(llm_response, title="🤖 Lokales LLM Experten-Feedback (Ollama)", border_style="magenta"))
    console.print()

def run_mock_ui():
    console = Console()
    layout = make_layout()
    layout["header"].update(Panel(f"[bold gold1]💎 AI TradingBot - Perfect Fit Dashboard (Ziel: {MAX_EPOCHS} Epochen)[/bold gold1]", style="white on dark_blue"))
    
    history_len = 50
    equity_data = [1000]
    train_loss_data = [2.0]
    val_loss_data = [2.1]
    acc_data = [0.4]
    conf_data = [0.1]
    
    stats = {}
    start_time = time.time()
    
    print("Starte gefixte Matrix-UI... (Drücke STRG+C zum Beenden)")
    time.sleep(1)

    try:
        with Live(layout, refresh_per_second=8, screen=True, console=console):
            for epoch in range(1, MAX_EPOCHS + 1):
                # Daten simulieren
                last_eq = equity_data[-1]
                equity_data.append(last_eq + random.uniform(-5, 8) + (epoch * 0.005))
                
                base_loss = 2.0 * math.exp(-epoch / 200)
                train_loss_data.append(base_loss + random.uniform(0, 0.05))
                v_loss = base_loss + random.uniform(0, 0.1) + (epoch * 0.0001)
                val_loss_data.append(v_loss)
                
                acc = 0.4 + 0.3 * (1 - math.exp(-epoch / 300)) + random.uniform(-0.02, 0.02)
                acc_data.append(acc)
                
                conf_data.append(0.1 + 0.7 * (1 - math.exp(-epoch / 400)) + random.uniform(-0.05, 0.05))

                # Stats speichern für die Zusammenfassung später
                stats = {
                    "epochs": epoch,
                    "final_eq": equity_data[-1],
                    "best_eq": max(equity_data),
                    "final_acc": acc_data[-1],
                    "best_acc": max(acc_data),
                    "final_loss": val_loss_data[-1],
                    "min_loss": min(val_loss_data),
                    "duration": time.time() - start_time
                }

                for arr in [equity_data, train_loss_data, val_loss_data, acc_data, conf_data]:
                    if len(arr) > history_len: arr.pop(0)

                # UI Update
                layout["metrics"].update(Panel(get_metrics_table(epoch, v_loss, acc, acc * 10)))
                layout["system_stats"].update(Panel("System Running...\n[dim]Drücke STRG+C für Report[/dim]", title="Logs"))
                
                layout["graph_equity"].update(Panel(PlotextRenderable(equity_data, "PnL", "cyan"), title="Portfolio PnL"))
                layout["graph_acc"].update(Panel(PlotextRenderable(acc_data, "Acc", "green"), title="Accuracy"))
                layout["graph_loss"].update(Panel(PlotextRenderable(
                    train_loss_data, "Train", "blue", val_loss_data, "Val", "red"
                ), title="Train vs Val Loss"))
                layout["graph_conf"].update(Panel(PlotextRenderable(conf_data, "Conf", "magenta"), title="Confidence"))
                
                progress_bar = "█" * int((epoch/MAX_EPOCHS)*40) + "░" * (40 - int((epoch/MAX_EPOCHS)*40))
                layout["footer"].update(Panel(f"Epoch [{progress_bar}] {(epoch/MAX_EPOCHS)*100:.1f}% | [yellow]Drücke STRG+C für Report[/yellow]"))
                
                time.sleep(0.02) # Etwas schneller gemacht, damit man auch ohne STRG+C ankommt
                
    except KeyboardInterrupt:
        pass # Wenn abgebrochen wird, fangen wir es auf und machen trotzdem den Report
    
    # Wenn die Schleife durchläuft (100%) ODER per STRG+C abgebrochen wird, zeige die Zusammenfassung
    show_summary(console, stats)

if __name__ == "__main__":
    run_mock_ui()
