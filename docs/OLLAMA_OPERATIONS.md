# Ollama — Betrieb (How-to)

Kurz und praktisch: wie Ollama auf diesem Mac läuft und wie sich mehrere
Pipelines (DigQDA, DINOH, …) einen Server teilen.

## Die drei Schichten

- **Homebrew (`brew`)** — installiert Ollama und hält es per `brew services` im
  Hintergrund am Laufen. Rechnet selbst nichts.
- **Ollama** — der lokale Modell-*Server* + CLI. Läuft auf
  `http://localhost:11434`, besitzt den Model-Store (`~/.ollama/models`).
- **Clients (DigQDA, DINOH, …)** — laufen als Python auf dem Mac und rufen die
  Ollama-API für den Modellschritt. Sie laufen *nicht* „auf ollama"; sie fragen ollama.

> **brew betreibt → ollama bedient Modelle → Clients fragen ollama.**

## Server: einmal einrichten, dann laufen lassen

```bash
brew services start ollama                          # Hintergrunddienst (Auto-Start bei Login)
curl -s http://localhost:11434/api/version; echo    # läuft? zeigt die Version
brew services list | grep ollama                    # Status
```

Genau **eine** Ollama. Nicht zusätzlich die Ollama-App laufen lassen — zwei Server
um Port 11434 sind ein Konflikt. Prüfen mit `which -a ollama` (nur ein Pfad).

## Modelle

```bash
ollama pull <tag>     # Modell holen, z. B. gemma4:12b
ollama list           # alles Heruntergeladene
ollama ps             # was gerade in den RAM geladen ist
```

Der Model-Store ist geteilt: alle Clients ziehen aus demselben Pool. Das koppelt
die Systeme nicht — getrennter Code, geteilte Infrastruktur.

## Mehrere Pipelines

- **Ein Server, viele Clients.** Ollama läuft einmal; DigQDA und DINOH reden beide
  mit `:11434`. Kein Ollama pro Pipeline, nicht pro Lauf stoppen/starten.
- **Speicher ist der Engpass.** Auf diesem M3 stehen ~11,8 GB für Ollama bereit —
  *ein* großes Modell (~8–10 GB) passt, **zwei gleichzeitig nicht**. Modellschritte
  also **nacheinander** laufen lassen; Ollama lädt/entlädt automatisch. `ollama ps`
  zeigt, was gerade resident ist.
- **Modell pro Lauf über den Tag** (`--model <tag>`). DigQDA und DINOH dürfen
  verschiedene Modelle gegen denselben Server nutzen.

## Upgrade / Restart

```bash
brew upgrade ollama
brew services restart ollama
```

Nur **zwischen** Läufen upgraden/neustarten — mitten in einem Request bricht der
Lauf ab (bei DigQDA sauber fail-closed, keine Korruption). Der Model-Store bleibt
beim Upgrade erhalten. DigQDA schreibt Tag + Digest + Server-/Client-Version in
jedes Manifest — der Lauf ist damit auch am geteilten Dauer-Server reproduzierbar.

## Wenn's klemmt

- `could not connect to ollama server` → `brew services start ollama`, kurz warten.
- Modell „not installed", obwohl geladen → falscher/zweiter Server. `which -a ollama`,
  Ollama-App beenden, `brew services restart ollama`, dann `ollama list`.
- Version zu alt für ein neues Modell → `brew upgrade ollama` (oder neueste
  Ollama-App), danach `curl …/api/version` prüfen.
