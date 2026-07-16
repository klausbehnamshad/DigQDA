# Lizenz-Entscheidung (Entwurf / DRAFT)

Status: **offen — vor öffentlichem Remote zu klären.** Diese Notiz empfiehlt, sie
entscheidet nicht.

## 0. Zuerst: Wer ist überhaupt Urheber/Rechteinhaber?

Das ist **keine technische, sondern eine institutionelle Frage** — und sie kommt
vor der Lizenzwahl. Software, die im Rahmen einer Anstellung oder eines
geförderten Projekts entsteht, gehört in vielen europäischen Universitäten
(inkl. Luxemburg üblich) **nicht automatisch der Einzelperson**, sondern der
Trägerinstitution; viele Häuser haben zudem eine eigene Open-Source-Release-
Policy und ein Tech-Transfer-/Legal-Office, das einer Veröffentlichung zustimmen
muss.

Zu klären, bevor eine Lizenz gesetzt wird:

- Hält **du persönlich** oder die **Universität / das Zentrum** das Copyright?
- Gibt es eine institutionelle **OSS-Release-Freigabe** (analog zur DPO-Freigabe
  auf der Datenseite)?
- Wer wird in der Copyright-Zeile der Lizenz genannt?

Die DPO hat die *Datenverarbeitung* freigegeben; die *Software-Veröffentlichung*
ist ein zweiter, eigener institutioneller Vorgang.

## 1. Empfehlung zur Lizenz (sobald Rechteinhaber geklärt)

Für ein wiederverwendbares Methoden-Toolkit, das gefunden, zitiert und breit
adaptiert werden soll:

- **Primär: Apache-2.0** für das ganze Repo. Permissiv (maximale Nachnutzung),
  **expliziter Patent-Grant** (schützt Nutzende, falls je eine Methode/Technik
  patent-berührt wäre), klare Trademark-Abgrenzung, `NOTICE`-Mechanismus für
  Attribution. Institutionsfreundlich.
- **Alternative: MIT**, wenn Minimalismus wichtiger ist als der Patent-Grant.
- **Optional zusätzlich: CC-BY-4.0** nur für die *Prompt-/Doku-Inhalte*, falls du
  für die methodischen Texte ausdrücklich eine Content-Lizenz mit Attribution
  willst. Sauber, aber Doppellizenz erhöht die Komplexität — im Zweifel Apache-2.0
  für alles + `CITATION.cff` für die wissenschaftliche Zitation genügt.

Zitation (akademische Attribution) läuft über `CITATION.cff` + DOI, nicht über die
Lizenz — beides ergänzt sich.

## 2. Umsetzung (nach Entscheidung)

- SPDX-Kennung oben in Quell-/Promptdateien, z.B. `SPDX-License-Identifier: Apache-2.0`.
- Vollständigen Lizenztext als `LICENSE` ablegen (Standardtext; ich lege ihn ein,
  sobald Rechteinhaber + Wahl feststehen).
- Copyright-Zeile: `Copyright <Jahr> <Rechteinhaber laut §0>`.
- In der README einen kurzen Lizenz-Abschnitt + (später) DOI-Badge.
