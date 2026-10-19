# Data report — 2026.10.0

Version date: 2026-10-19 · as of: 2026-10-19 · mode: release

## Status

**PASS** — 0 errors, 16 warnings, 0 pending acceptances, 96 vectors.

## Warnings

- [curation] vla_designations.csv:444: vnr-besl-2025-116 designates fluvius-limburg (gas) in 73109, the data does not
- [curation] wal_designations.csv:258: agw-aieg-brunehaut-2022 designates ores (elec) in 57093, the data does not
- [curation] wal_designations.csv:266: agw-aiesh-elec-2022 designates ores (elec) in 93014, the data does not
- [curation] spot_checks.csv:8: cwape-powerbi-grd-elec-2026-10-12 on 2026-10-12 shows ores (elec) in 57093 (matches=false) (explained: valid_from 2026-01-01, to_confirm)
- [curation] spot_checks.csv:17: cwape-powerbi-grd-gas-2026-10-12 on 2026-10-12 shows none (gas) in 62026 (matches=false) (explained: a designation does not guarantee a network)
- [curation] spot_checks.csv:33: cwape-powerbi-grd-gas-2026-10-12 on 2026-10-12 shows none (gas) in 63067 (matches=false) (explained: valid_from 2026-06-01, a designation does not guarantee a network)
- [curation] spot_checks.csv:46: cwape-powerbi-grd-elec-2026-10-12 on 2026-10-12 shows ores (elec) in 93014 (matches=false) (explained: valid_from 2024-01-01)
- [cross-check] Fluvius 2070 Burcht: fluvius-antwerpen/fluvius-antwerpen, data fluvius-midden-vlaanderen/fluvius-midden-vlaanderen (explained: valid_from 2026-01-01)
- [cross-check] Fluvius 2070 Zwijndrecht: fluvius-antwerpen/fluvius-antwerpen, data fluvius-midden-vlaanderen/fluvius-midden-vlaanderen (explained: valid_from 2026-01-01)
- [cross-check] CWaPE Power BI gas, 25107 Villers-la-Ville: no GRD shown; data ores (explained: a designation does not guarantee a network)
- [cross-check] CWaPE Power BI gas, 25122 Ramillies: no GRD shown; data ores (explained: a designation does not guarantee a network)
- [cross-check] CWaPE Power BI elec, 57093 Brunehaut: ORES Hainaut 19; data aieg (explained: valid_from 2026-01-01, to_confirm)
- [cross-check] CWaPE Power BI gas, 62026 Comblain-au-Pont: no GRD shown; data resa (explained: a designation does not guarantee a network)
- [cross-check] CWaPE Power BI gas, 63067 Saint-Vith: no GRD shown; data resa (explained: valid_from 2026-06-01, a designation does not guarantee a network)
- [cross-check] CWaPE Power BI gas, 85046 Habay: no GRD shown; data ores (explained: a designation does not guarantee a network)
- [cross-check] CWaPE Power BI elec, 93014 Couvin: AIESH 30 + ORES Namur 10; data aiesh (explained: valid_from 2024-01-01)

## Inputs

| file | sha256 |
|---|---|
| assignments.csv | a865a11c8d59ffa6dd8084672152ee74dceb9486b4f6d78926d2757999faf679 |
| communes.csv | 67376dc4d635bb557c914391de77203cdf6eb9b684acdbf49f1db9d057b1d2b0 |
| notes.csv | 878457c843688b2c55d2e8c7e9d9575386898113f3ab0f23d3ec00f34783c5df |
| operators.csv | e71a41d5d4c472594f5fd4a4df189469b6511c35dddc54cc3c88c122971960d6 |
| postcodes.csv | d4fd81b43808ee1e12e5cee3deb18904f6b465d978cb764afc4e4ba3f5718637 |
| sections.csv | 3172dec0603d2151e9306b9f28df0020165a4e2ae303d7f77682ec61eb1912be |
| sources.csv | 2033940e963479834d6e7a317db7db904dcfc55bdc4a329546f2f362d07af8ec |

## Counts

| region | communes | sections | published rows |
|---|---|---|---|
| BRU | 19 | 0 | 24 |
| VLA | 285 | 2 | 523 |
| WAL | 261 | 2 | 606 |

Postcodes: 1149 distinct, 1152 (postcode, INS) pairs; shared by several communes: 1040, 1050, 1804.

## Electricity

| operator | communes operated | communes designated |
|---|---|---|
| aieg | 6 | 6 |
| aiesh | 6 | 6 |
| fluvius-antwerpen | 28 | 28 |
| fluvius-halle-vilvoorde | 29 | 29 |
| fluvius-imewo | 38 | 38 |
| fluvius-kempen | 27 | 27 |
| fluvius-limburg | 39 | 39 |
| fluvius-midden-vlaanderen | 21 | 21 |
| fluvius-west | 59 | 59 |
| fluvius-zenne-dijle | 44 | 44 |
| ores | 194 | 194 |
| resa | 54 | 54 |
| rew | 1 | 1 |
| sibelga | 19 | 19 |

Flanders against the spec's VREG list (unsourced in the spec):

| DSO | expected | found |
|---|---|---|
| fluvius-antwerpen | 28 | 28 |
| fluvius-halle-vilvoorde | 29 | 29 |
| fluvius-imewo | 38 | 38 |
| fluvius-kempen | 27 | 27 |
| fluvius-limburg | 39 | 39 |
| fluvius-midden-vlaanderen | 21 | 21 |
| fluvius-west | 59 | 59 |
| fluvius-zenne-dijle | 44 | 44 |

ORES designated in 194 Walloon communes; the 2022 opinion lists 190, 194 after the known changes:

- Bastogne absorbed Bertogne on 02/12/2024 (Walloon decree of 19/05/2023, art. 2; both in the 190)
- Profondeville: AGW of 15/07/2022
- Hamoir and Jemeppe-sur-Sambre: AGW of 01/07/2022
- Philippeville: AGWs of 01/07/2022 and 12/10/2023
- Brugelette: AGW of 08/12/2022

## Gas

| status | operator | attributions |
|---|---|---|
| designated | fluvius-antwerpen | 28 |
| designated | fluvius-halle-vilvoorde | 29 |
| designated | fluvius-imewo | 38 |
| designated | fluvius-kempen | 27 |
| designated | fluvius-limburg | 38 |
| designated | fluvius-midden-vlaanderen | 21 |
| designated | fluvius-west | 59 |
| designated | fluvius-zenne-dijle | 44 |
| designated | ores | 118 |
| designated | resa | 59 |
| designated | sibelga | 19 |
| foreign | enexis | 1 |
| none | - | 86 |

## Flagged attributions

| INS | commune | section | flags | note | FR note | accepted |
|---|---|---|---|---|---|---|
| 46030 | Beveren-Kruibeke-Zwijndrecht | - | transition | zwijndrecht-2026 | Depuis le 01/01/2026, toute la commune de Beveren-Kruibeke-Zwijndrecht dépend de Fluvius Midden-Vlaanderen pour l'électricité et le gaz. Auparavant, Zwijndrecht (2070) dépendait de Fluvius Antwerpen (décisions BESL-2025-70, BESL-2025-71 et BESL-2026-30 du régulateur flamand). | accepted 2026-10-19 |
| 57093 | Brunehaut | - | transition\|to_confirm | brunehaut-2026 | Depuis le 01/01/2026, l'AIEG gère le réseau d'électricité de Brunehaut à la place d'ORES (arrêté du Gouvernement wallon du 05/05/2022 ; rapports 2025 d'ORES Assets et de l'AIEG). Pour le gaz, la désignation d'IGH a pris fin le 01/01/2023 et aucune désignation ultérieure n'a été trouvée : l'absence de gestionnaire de réseau de gaz est à confirmer. | accepted 2026-10-19 |
| 61039 | Marchin | - | to_confirm | marchin-gas | Selon la CWaPE, RESA distribue du gaz naturel à Marchin. Aucun arrêté désignant un gestionnaire de réseau de gaz naturel pour Marchin n'a toutefois été trouvé (la commune n'est citée dans aucun arrêté de désignation de RESA pour le gaz) : à confirmer. | accepted 2026-10-19 |
| 62026 | Comblain-au-Pont | - | propane_note | propane-comblain-poulseur | Le gaz naturel de Comblain-au-Pont est distribué par RESA. La cité de Poulseur n'est pas raccordée au réseau de gaz naturel : RESA y distribue du propane par un réseau local, une activité qu'il doit cesser au plus tard le 31/12/2027 (arrêté du Gouvernement wallon du 24/04/2025). | accepted 2026-10-19 |
| 62032 | Esneux | - | propane_note | propane-esneux-fontin | Le gaz naturel d'Esneux est distribué par RESA. La cité de Fontin n'est pas raccordée au réseau de gaz naturel : RESA y distribue du propane par un réseau local, une activité qu'il doit cesser au plus tard le 31/12/2027 (arrêté du Gouvernement wallon du 24/04/2025). | accepted 2026-10-19 |
| 62108 | Visé | - | propane_note | propane-vise-lixhe | Le gaz naturel de Visé est distribué par RESA. La cité de Lixhe n'est pas raccordée au réseau de gaz naturel : RESA y distribue du propane par un réseau local, une activité qu'il doit cesser au plus tard le 31/12/2027 (arrêté du Gouvernement wallon du 24/04/2025). | accepted 2026-10-19 |
| 63067 | Saint-Vith | - | transition | saint-vith-gas | Depuis le 01/06/2026, RESA est le gestionnaire désigné du réseau de gaz naturel à Saint-Vith (arrêté du Gouvernement wallon du 25/06/2026). La commune n'avait pas de réseau de gaz naturel avant cette désignation. | accepted 2026-10-19 |
| 92054 | Gesves | - | transition\|to_confirm | gesves-2026-operator-change | L'AIEG est le gestionnaire désigné du réseau d'électricité de Gesves (arrêté du Gouvernement wallon du 24/03/2022). Un échange de réseaux entre ORES et l'AIEG a été décidé avec effet au 01/07/2026. Le réseau est aujourd'hui exploité par l'AIEG. Aucune source publique ne confirme encore que l'échange est achevé : à confirmer. | accepted 2026-10-19 |
| 92094 | Namur | - | transition\|to_confirm | namur-2026-operator-change | ORES est le gestionnaire désigné du réseau d'électricité de toute la commune de Namur (arrêté du Gouvernement wallon du 09/06/2022). Un échange de réseaux entre ORES et l'AIEG a été décidé avec effet au 01/07/2026. Le réseau est aujourd'hui exploité par ORES. Aucune source publique ne confirme encore que l'échange est achevé : à confirmer. | accepted 2026-10-19 |
| 93088 | Walcourt | - | to_confirm | walcourt-gas | Selon la CWaPE et les données ouvertes d'ORES, ORES distribue du gaz naturel à Tarcienne (Walcourt). Aucun arrêté désignant un gestionnaire de réseau de gaz naturel pour Walcourt n'a toutefois été trouvé : à confirmer. | accepted 2026-10-19 |

Dataset-level notes:

| key | FR note | accepted |
|---|---|---|
| dataset-vla-designations-2026 | Les désignations des gestionnaires de réseau d'électricité en Flandre couraient jusqu'au 05/09/2026, sauf à Fourons, où Fluvius Limburg est désigné jusqu'au 01/01/2028 (décision BESL-2016-31 du régulateur flamand). Fluvius en a demandé le renouvellement (conseils d'administration des gestionnaires de réseau en mars 2026, assemblées générales en juin 2026) ; au 12/10/2026, le régulateur flamand n'a publié aucune décision. Les gestionnaires indiqués sont ceux en place au 01/01/2026. | accepted 2026-10-19 |

## Transitions and operator_differs

| INS | section | operator | designated | valid_from | flags |
|---|---|---|---|---|---|
| 46030 | - | fluvius-midden-vlaanderen | fluvius-midden-vlaanderen | 2026-01-01 | transition |
| 57093 | - | aieg | aieg | 2026-01-01 | transition\|to_confirm |
| 63067 | - | ores | ores | 2026-06-01 | transition |
| 92054 | - | aieg | aieg | 2026-07-01 | transition\|to_confirm |
| 92094 | - | ores | ores | 2026-07-01 | transition\|to_confirm |

## Sources

| id | role | publisher | attributions | retrieved_at | age (days) |
|---|---|---|---|---|---|
| agw-2009-04-23-alg-gaz-waimes | R | Gouvernement wallon (Moniteur belge) | 1 | 2026-10-12 | 7 |
| agw-2022-05-25-resa-gaz | R | Gouvernement wallon (Moniteur belge) | 140 | 2026-10-12 | 7 |
| agw-2022-06-09-ores-gaz | R | Gouvernement wallon (Moniteur belge) | 198 | 2026-10-12 | 7 |
| agw-2022-07-01-ores-gaz-jemeppe | R | Gouvernement wallon (Moniteur belge) | 1 | 2026-10-12 | 7 |
| agw-2022-07-01-resa-gaz-comblain | R | Gouvernement wallon (Moniteur belge) | 1 | 2026-10-12 | 7 |
| agw-2022-10-27-resa-gaz-trooz | R | Gouvernement wallon (Moniteur belge) | 1 | 2026-10-12 | 7 |
| agw-2022-12-08-ores-gaz-brugelette | R | Gouvernement wallon (Moniteur belge) | 1 | 2026-10-12 | 7 |
| agw-2022-12-08-ores-gaz-hamois | R | Gouvernement wallon (Moniteur belge) | 1 | 2026-10-12 | 7 |
| agw-2022-12-15-ores-gaz-fernelmont | R | Gouvernement wallon (Moniteur belge) | 1 | 2026-10-12 | 7 |
| agw-2024-04-19-ores-gaz-fernelmont | R | Gouvernement wallon (Moniteur belge) | 1 | 2026-10-12 | 7 |
| agw-2024-05-30-resa-gaz-esneux | R | Gouvernement wallon (Moniteur belge) | 1 | 2026-10-12 | 7 |
| agw-2025-04-24-resa-propane | R | Gouvernement wallon (Moniteur belge) | 3 | 2026-10-12 | 7 |
| agw-2026-06-25-resa-gaz-saint-vith | R | Gouvernement wallon (Moniteur belge) | 1 | 2026-10-12 | 7 |
| agw-aieg-brunehaut-2022 | R | Gouvernement wallon (Moniteur belge) | 1 | 2026-10-12 | 7 |
| agw-aieg-elec-2022 | R | Gouvernement wallon (Moniteur belge) | 4 | 2026-10-12 | 7 |
| agw-aieg-gesves-2022 | R | Gouvernement wallon (Moniteur belge) | 1 | 2026-10-12 | 7 |
| agw-aiesh-elec-2022 | R | Gouvernement wallon (Moniteur belge) | 6 | 2026-10-12 | 7 |
| agw-ores-brugelette-2022 | R | Gouvernement wallon (Moniteur belge) | 1 | 2026-10-12 | 7 |
| agw-ores-elec-2022 | R | Gouvernement wallon (Moniteur belge) | 190 | 2026-10-12 | 7 |
| agw-ores-hamoir-jemeppe-2022 | R | Gouvernement wallon (Moniteur belge) | 2 | 2026-10-12 | 7 |
| agw-ores-philippeville-2022 | R | Gouvernement wallon (Moniteur belge) | 1 | 2026-10-12 | 7 |
| agw-ores-philippeville-2023 | R | Gouvernement wallon (Moniteur belge) | 1 | 2026-10-12 | 7 |
| agw-ores-profondeville-2022 | R | Gouvernement wallon (Moniteur belge) | 1 | 2026-10-12 | 7 |
| agw-resa-comblain-fexhe-2022 | R | Gouvernement wallon (Moniteur belge) | 2 | 2026-10-12 | 7 |
| agw-resa-elec-2022 | R | Gouvernement wallon (Moniteur belge) | 51 | 2026-10-12 | 7 |
| agw-resa-esneux-2024 | R | Gouvernement wallon (Moniteur belge) | 1 | 2026-10-12 | 7 |
| agw-resa-trooz-2022 | R | Gouvernement wallon (Moniteur belge) | 1 | 2026-10-12 | 7 |
| agw-rew-wavre | R | Gouvernement wallon (Moniteur belge) | 1 | 2026-10-12 | 7 |
| aieg-communes | C | AIEG | 6 | 2026-10-12 | 7 |
| aieg-ra-2025 | C | AIEG | 3 | 2026-10-12 | 7 |
| aiesh-communes | C | AIESH | 6 | 2026-10-12 | 7 |
| brugel-avis-204 | C | Brugel | 19 | 2026-10-12 | 7 |
| brugel-grd | R | Brugel | 19 | 2026-10-12 | 7 |
| cwape-avis-0892-resa-elec | C | CWaPE | 50 | 2026-10-12 | 7 |
| cwape-avis-0893-resa-gaz | C | CWaPE | 54 | 2026-10-12 | 7 |
| cwape-avis-0900-ores-gaz | C | CWaPE | 113 | 2026-10-12 | 7 |
| cwape-avis-0904-ores-gaz-jemeppe | C | CWaPE | 1 | 2026-10-12 | 7 |
| cwape-avis-0905-resa-elec-comblain-fexhe | C | CWaPE | 2 | 2026-10-12 | 7 |
| cwape-avis-0906-resa-gaz-comblain | C | CWaPE | 1 | 2026-10-12 | 7 |
| cwape-avis-0913-resa-trooz | C | CWaPE | 1 | 2026-10-12 | 7 |
| cwape-avis-0914-resa-gaz-trooz | C | CWaPE | 1 | 2026-10-12 | 7 |
| cwape-avis-0943-ores-gaz-fernelmont | C | CWaPE | 1 | 2026-10-12 | 7 |
| cwape-avis-0948-resa-elec-esneux | C | CWaPE | 1 | 2026-10-12 | 7 |
| cwape-avis-0949-resa-gaz-esneux | C | CWaPE | 1 | 2026-10-12 | 7 |
| cwape-avis-0957-resa-propane | C | CWaPE | 3 | 2026-10-12 | 7 |
| cwape-avis-0976-resa-gaz-saint-vith | C | CWaPE | 1 | 2026-10-12 | 7 |
| cwape-decision-0842-aiesh-couvin | C | CWaPE | 1 | 2026-10-12 | 7 |
| cwape-decision-aiesh-revenu-2025-2029 | C | CWaPE | 1 | 2026-10-12 | 7 |
| cwape-powerbi-grd-elec-2026-10-12 | C | CWaPE | 260 | 2026-10-12 | 7 |
| cwape-powerbi-grd-gas-2026-10-12 | C | CWaPE | 257 | 2026-10-12 | 7 |
| decret-2023-05-19-fusion-bastogne-bertogne | R | Parlement wallon (Moniteur belge) | 1 | 2026-10-12 | 7 |
| fluvius-1-23 | M | Fluvius | 285 | 2026-10-12 | 7 |
| fluvius-wijzigingen-2026 | C | Fluvius | 1 | 2026-10-12 | 7 |
| geo-statbel-nis6-2025 | M | Statbel | 0 | 2026-10-12 | 7 |
| geo-statbel-postcodes-2025 | M | Statbel | 0 | 2026-10-12 | 7 |
| geo-statbel-refnis-2025 | M | Statbel | 0 | 2026-10-12 | 7 |
| gesves-2026-09-07-eclairage-public | C | Commune de Gesves | 1 | 2026-10-12 | 7 |
| namur-cc-2026-05-26-aieg | C | Ville de Namur | 1 | 2026-10-12 | 7 |
| namur-cc-2026-06-23-pv | C | Ville de Namur | 1 | 2026-10-12 | 7 |
| odwb-ores-elec | M | ORES | 195 | 2026-10-12 | 7 |
| odwb-ores-gas | M | ORES | 200 | 2026-10-12 | 7 |
| ores-ag-2026-05-21-point-06 | C | ORES | 2 | 2026-10-12 | 7 |
| ores-ag-2026-05-21-point-07 | C | ORES | 2 | 2026-10-12 | 7 |
| ores-ag-2026-05-21-pv | C | ORES | 1 | 2026-10-12 | 7 |
| ores-assets-ra-2025 | C | ORES | 1 | 2026-10-12 | 7 |
| ores-interruptions-namur-2026 | C | ORES | 1 | 2026-10-12 | 7 |
| resa-ra-2024 | C | RESA | 17 | 2026-10-12 | 7 |
| rew-historique | C | REW | 1 | 2026-10-12 | 7 |
| vnr-aanwijzing-netbeheerders | R | Vlaamse Nutsregulator | 2 | 2026-10-12 | 7 |
| vnr-besl-2015-43 | R | Vlaamse Nutsregulator | 2 | 2026-10-12 | 7 |
| vnr-besl-2015-47 | R | Vlaamse Nutsregulator | 1 | 2026-10-12 | 7 |
| vnr-besl-2016-31 | R | Vlaamse Nutsregulator | 1 | 2026-10-12 | 7 |
| vnr-besl-2025-104 | R | Vlaamse Nutsregulator | 28 | 2026-10-12 | 7 |
| vnr-besl-2025-105 | R | Vlaamse Nutsregulator | 29 | 2026-10-12 | 7 |
| vnr-besl-2025-106 | R | Vlaamse Nutsregulator | 38 | 2026-10-12 | 7 |
| vnr-besl-2025-107 | R | Vlaamse Nutsregulator | 28 | 2026-10-12 | 7 |
| vnr-besl-2025-108 | R | Vlaamse Nutsregulator | 39 | 2026-10-12 | 7 |
| vnr-besl-2025-109 | R | Vlaamse Nutsregulator | 21 | 2026-10-12 | 7 |
| vnr-besl-2025-110 | R | Vlaamse Nutsregulator | 59 | 2026-10-12 | 7 |
| vnr-besl-2025-111 | R | Vlaamse Nutsregulator | 44 | 2026-10-12 | 7 |
| vnr-besl-2025-112 | R | Vlaamse Nutsregulator | 28 | 2026-10-12 | 7 |
| vnr-besl-2025-113 | R | Vlaamse Nutsregulator | 29 | 2026-10-12 | 7 |
| vnr-besl-2025-114 | R | Vlaamse Nutsregulator | 38 | 2026-10-12 | 7 |
| vnr-besl-2025-115 | R | Vlaamse Nutsregulator | 27 | 2026-10-12 | 7 |
| vnr-besl-2025-116 | R | Vlaamse Nutsregulator | 38 | 2026-10-12 | 7 |
| vnr-besl-2025-117 | R | Vlaamse Nutsregulator | 21 | 2026-10-12 | 7 |
| vnr-besl-2025-118 | R | Vlaamse Nutsregulator | 59 | 2026-10-12 | 7 |
| vnr-besl-2025-119 | R | Vlaamse Nutsregulator | 44 | 2026-10-12 | 7 |
| vnr-besl-2025-70 | R | Vlaamse Nutsregulator | 1 | 2026-10-12 | 7 |
| vnr-besl-2025-71 | R | Vlaamse Nutsregulator | 1 | 2026-10-12 | 7 |
| vnr-besl-2026-30 | R | Vlaamse Nutsregulator | 1 | 2026-10-12 | 7 |

## Cross-check disagreements

- [curation] vla_designations.csv:444: vnr-besl-2025-116 designates fluvius-limburg (gas) in 73109, the data does not
- [curation] wal_designations.csv:258: agw-aieg-brunehaut-2022 designates ores (elec) in 57093, the data does not
- [curation] wal_designations.csv:266: agw-aiesh-elec-2022 designates ores (elec) in 93014, the data does not
- [curation] spot_checks.csv:8: cwape-powerbi-grd-elec-2026-10-12 on 2026-10-12 shows ores (elec) in 57093 (matches=false) (explained: valid_from 2026-01-01, to_confirm)
- [curation] spot_checks.csv:17: cwape-powerbi-grd-gas-2026-10-12 on 2026-10-12 shows none (gas) in 62026 (matches=false) (explained: a designation does not guarantee a network)
- [curation] spot_checks.csv:33: cwape-powerbi-grd-gas-2026-10-12 on 2026-10-12 shows none (gas) in 63067 (matches=false) (explained: valid_from 2026-06-01, a designation does not guarantee a network)
- [curation] spot_checks.csv:46: cwape-powerbi-grd-elec-2026-10-12 on 2026-10-12 shows ores (elec) in 93014 (matches=false) (explained: valid_from 2024-01-01)
- [cross-check] Fluvius 2070 Burcht: fluvius-antwerpen/fluvius-antwerpen, data fluvius-midden-vlaanderen/fluvius-midden-vlaanderen (explained: valid_from 2026-01-01)
- [cross-check] Fluvius 2070 Zwijndrecht: fluvius-antwerpen/fluvius-antwerpen, data fluvius-midden-vlaanderen/fluvius-midden-vlaanderen (explained: valid_from 2026-01-01)
- [cross-check] CWaPE Power BI gas, 25107 Villers-la-Ville: no GRD shown; data ores (explained: a designation does not guarantee a network)
- [cross-check] CWaPE Power BI gas, 25122 Ramillies: no GRD shown; data ores (explained: a designation does not guarantee a network)
- [cross-check] CWaPE Power BI elec, 57093 Brunehaut: ORES Hainaut 19; data aieg (explained: valid_from 2026-01-01, to_confirm)
- [cross-check] CWaPE Power BI gas, 62026 Comblain-au-Pont: no GRD shown; data resa (explained: a designation does not guarantee a network)
- [cross-check] CWaPE Power BI gas, 63067 Saint-Vith: no GRD shown; data resa (explained: valid_from 2026-06-01, a designation does not guarantee a network)
- [cross-check] CWaPE Power BI gas, 85046 Habay: no GRD shown; data ores (explained: a designation does not guarantee a network)
- [cross-check] CWaPE Power BI elec, 93014 Couvin: AIESH 30 + ORES Namur 10; data aiesh (explained: valid_from 2024-01-01)

## Open questions

- **Q2** Namur and Gesves: the ORES ↔ AIEG network exchange was decided to take effect on 01/07/2026; ORES operates Namur and the AIEG operates Gesves today; no public confirmation that the exchange is complete (to_confirm). The sources disagree on who operated these networks before the exchange; the notes stay neutral.
- **Q3** Saint-Vith gas: answered. The AGW of 25/06/2026 (MB 07/07/2026) designates RESA from 01/06/2026 to 01/06/2046; the row keeps `transition`. For Eric's information.
- **Q4** Flanders: the electricity designations ran until 05/09/2026 (Voeren until 01/01/2028, BESL-2016-31); Fluvius applied for their renewal; no regulator decision published as of 12/10/2026 (dataset note, or to_confirm everywhere).
- **G5** Brunehaut gas: no designation found after IGH ended on 01/01/2023 (to_confirm).
- **G20** Walcourt gas: ORES + to_confirm. ORES distributes gas at Tarcienne (CWaPE Power BI: ORES Namur 2; ORES open data: 7 to 8 access points a year, 2020-2024), but no designation order was found.
- **G21** Bastogne gas: two sections since the merger of 02/12/2024 (Walloon decree of 19/05/2023, art. 2). Bastogne (6600): ORES; Bertogne (6686-6688): no gas DSO, since the ORES gas order of 09/06/2022 names Bastogne only and ORES open data count no gas access point at 6686-6688.
- **G22** Marchin gas: RESA + to_confirm. The CWaPE Power BI shows RESA (1), but no designation order was found: Marchin is in none of RESA's gas orders.
- **Q5** Licence of the compiled data: answered. CC BY 4.0 by OptimCE (`LICENSE`); the sources keep their own licences and credits (`ATTRIBUTION.md`), the Statbel postcode file (derived by Statbel from bpost data) included. For Eric's information.
- **Q6** CWaPE Power BI « GRD par commune »: read by hand on 12/10/2026 (no export). It lags for Couvin (ORES Namur 10 beside AIESH 30; AIESH since 01/01/2024) and Brunehaut (ORES Hainaut 19; AIEG since 01/01/2026; electricity data 2026-T1): explained warnings. Habay, Ramillies, Villers-la-Ville (ORES) and Comblain-au-Pont (RESA) have a gas designation but no gas GRD on the map: kept designated. The full reading stays out of the public repository (licence not stated); `curation/powerbi_checks.csv` keeps the comparison of each Walloon row.
- **Q7** The Sibelga EAN prefix 5414489 also starts the Liège demo EANs (RESA).
