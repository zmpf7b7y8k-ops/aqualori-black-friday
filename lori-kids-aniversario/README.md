# Lôri Kids — Campanha de Aniversário (5 anos)

Projeto independente da campanha de Black Friday da Aqualôri. Nenhum arquivo, cor, fonte ou elemento visual daquela campanha foi reutilizado.

## Entrega
`export/LoriKids_5anos_Reels_1080x1920.mp4`: H.264 High, 1080×1920 (9:16), 30 fps, 35,8 s, AAC estéreo 256 kbps, áudio em −14 LUFS. Pronto para Reels.

## Identidade da campanha
- **Cores:** laranja `#F37032`, amarelo `#FFC83D`, verde-folha `#3E8E4E`, verde-profundo `#1F4D34`, sálvia `#B9CBA3`, creme `#FFF6E7`. Tons tirados da decoração da loja (paredes sálvia, copa da árvore, logo laranja, parede amarela).
- **Tipografia:** Fredoka (títulos e números) e Nunito (apoio), ambas arredondadas e de licença OFL, em `fontes/`.
- **Motivos gráficos:** disco do "5" com anel, pílulas, confetes geométricos discretos e a borda "copa de árvore" do espaço kids.

## Estrutura da edição
| Tempo | Cena | Destaques |
|-------|------|-----------|
| 0–5,7 s | Clipe 1, aniversário | Abertura em anéis concêntricos; "ESSA SEMANA É / MUITO / ESPECIAL"; "A NOSSA / LÔRI KIDS / COMPLETA"; disco com "5" em volume, "ANOS" |
| 5,7–13,7 s | Clipe 2, sorteio | Transição: mergulho no disco e abertura em íris; legendas; cartão "SORTEIO ESPECIAL / CONCORRA A UM SKATENET"; cantoneiras que acompanham o produto |
| 13,7–24,5 s | Clipe 3, como participar | Faixas diagonais; "PARA PARTICIPAR / É MUITO FÁCIL"; vídeo vira janela; "DE QUARTA A SÁBADO" com os dias 25–28/11; "A CADA R$ 50 EM COMPRAS" com números rolando; cupom "1 CUPOM PARA CONCORRER" |
| 24,5–35,8 s | Clipe 4, encerramento | Transição "copa de árvore"; legendas; selo "5 ANOS"; "5 ANOS DE LÔRI KIDS"; assinatura com "VENHA COMEMORAR COM A GENTE!" e as datas |

Cortes internos removem pausas e ficam disfarçados por reenquadramentos. Cada clipe tem correção de cor própria. O áudio é só a fala original (sem música nem efeitos), nivelado entre os clipes.

## Como regenerar
`src/build.sh <pasta com os .mov originais> <pasta de trabalho>`. Usa `src/render.py` (compositor em skia-python) e `src/track_faces.py`.
Os vídeos brutos não estão versionados.
