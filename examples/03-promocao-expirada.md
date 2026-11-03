# Promoção expirada (cenário não trivial)

O Takamine GD20 tem uma promoção de 12% cadastrada com is_active = 0. O cliente pergunta justamente por ela. O agente precisa informar o preço atual e não prometer um desconto que não está mais vigente (manual, seção 7.3).

> Gerado por `scripts/generate_examples.py` · modelo `claude-haiku-5-5` · data de referência do agente: 2026-03-23

---

**cliente:** quanto custa o Takamine GD20?

<sub>🔧 search_products(term='takamine GD20')</sub>

**Dani:** O Takamine GD20 Dreadnought Natural está por R$ 2.199,00. No PIX sai por R$ 2.089,05, com o desconto de 5%.

Está disponível, com 5 unidades em estoque. Quer que eu veja as opções de parcelamento no cartão ou o valor do frete para sua cidade?

**cliente:** ué, eu vi num anúncio que tinha 12% de desconto nele. ainda vale?

<sub>🔧 active_promotions()</sub>

**Dani:** Não encontrei nenhuma promoção de 12% no Takamine GD20 hoje, então esse anúncio deve ser de uma campanha que já encerrou. O preço vigente dele é R$ 2.199,00, e no PIX fica R$ 2.089,05 (5% de desconto). Ele está com 5 unidades em estoque.

Se quiser, posso ver outras opções nessa faixa de preço para comparar.

**cliente:** e tem alguma promoção rolando hoje então?

**Dani:** Hoje estão rolando estas promoções:

- Ohana CK-20 Concert Natural (ukulele): de R$ 549,00 por R$ 439,20, com 20% de desconto. Tem 6 em estoque.
- Crafter HT-100 Folk Aço Natural (violão): de R$ 2.399,00 por R$ 1.967,18, com 18% de desconto. Tem 3 em estoque.
- Kalani KAL-700T Tenor Natural (ukulele): de R$ 359,00 por R$ 323,10, com 10% de desconto. Tem 11 em estoque.
- Taylor 110e Dreadnought Natural (violão): de R$ 5.999,00 por R$ 5.519,08, com 8% de desconto. Tem 4 em estoque.

Nessas promoções o desconto de 5% do PIX não se aplica. Quer que eu veja as condições de pagamento de alguma delas?
