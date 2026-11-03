# Catálogo com filtro de preço

O cliente dá uma faixa de preço e o agente consulta o catálogo em vez de responder de memória. O filtro roda sobre o preço que o cliente de fato paga, não sobre o de tabela.

> Gerado por `scripts/generate_examples.py` · modelo `claude-haiku-5-5` · data de referência do agente: 2026-03-23

---

**cliente:** oi! quais opções de violões disponíveis custando até R$1000?

<sub>🔧 search_products(category='Violões', max_price=1000) · active_promotions()</sub>

**Dani:** Tenho 8 violões disponíveis até R$ 1.000. Os preços são no cartão, e o PIX dá 5% de desconto:

- Tagima Memphis AC-39 Nylon Natural: R$ 429,90 (PIX R$ 408,40), 15 em estoque
- Rozini RC-104 Nylon Estudante: R$ 459,90 (PIX R$ 436,90), 10 em estoque
- Shelby SN-100 Folk Aço Preto: R$ 549,00 (PIX R$ 521,55), 5 em estoque
- Giannini GF-1R Aço Folk Sunburst: R$ 579,90 (PIX R$ 550,90), 7 em estoque
- Yamaha C40 Nylon Natural: R$ 599,90 (PIX R$ 569,90), 12 em estoque
- Giannini GN-15 Nylon Cedro Natural: R$ 689,00 (PIX R$ 654,55), 6 em estoque
- Yamaha F310 Aço Natural: R$ 699,90 (PIX R$ 664,90), 14 em estoque
- Tagima Dallas Tuner Aço Natural: R$ 749,00 (PIX R$ 711,55), 9 em estoque

Não há promoção ativa nessa faixa de preço para violões. Se você quiser cordas de aço ou de nylon, é só falar que eu filtro. Também posso detalhar algum modelo específico. Ficou faltando alguma coisa?

**cliente:** o Yamaha F310 é bom pra quem tá começando?

<sub>🔧 product_details(product_id=87)</sub>

**Dani:** Pelo que a ficha traz, sim, ele é uma escolha bem comum pra quem está começando. A descrição diz que é um dos modelos mais vendidos da Yamaha para iniciantes e intermediários, com corpo robusto e timbre encorpado.

Algumas especificações: tampo de Spruce (picea), laterais e fundo de Meranti, braço de Nato, cordas de aço, escala de 634 mm e sem captação elétrica. Ele é só acústico, então serve para tocar em casa ou em roda, mas não liga em amplificador.

Preço: R$ 699,90, ou R$ 664,90 no PIX. Tem 14 unidades em estoque.

Se você quer algo mais leve no toque e mais barato, o Yamaha C40 de nylon (R$ 599,90) é outra opção comum para começar. As cordas de nylon são mais macias nos dedos, mas o som é diferente do aço. Ficou alguma dúvida?

**cliente:** quanto fica no pix?

**Dani:** No PIX, o Yamaha F310 sai por R$ 664,90. É o preço de R$ 699,90 com o desconto de 5%. Ele não está em promoção, então o desconto do PIX vale.

Ficou faltando alguma coisa?
