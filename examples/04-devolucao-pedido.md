# Devolução com cálculo de prazo (cenário não trivial)

O agente cruza dois mundos: o pedido (data de entrega, vinda do CSV) e a política (janela de 7 dias para arrependimento). O prazo do pedido 7 já venceu, então a resposta certa é negar com transparência — e apontar a garantia legal de 90 dias, que ainda está de pé.

> Gerado por `scripts/generate_examples.py` · modelo `claude-haiku-5-5` · data de referência do agente: 2026-03-23

---

**cliente:** me arrependi da minha compra, posso devolver meu pedido?

<sub>🔧 search_policies(question='devolução por arrependimento prazo')</sub>

**Dani:** Dá para sim, pode devolver. Pela nossa política, em compras online você tem até 7 dias corridos após o recebimento para pedir a devolução, sem precisar justificar. O produto precisa voltar na embalagem original, sem sinais de uso, com todos os acessórios e manuais. O reembolso sai na mesma forma de pagamento usada na compra, em até 10 dias úteis, e o frete da devolução fica por conta da loja.

Para eu conferir o seu pedido e os prazos certinhos, me manda o número do pedido, por favor. Ele aparece na confirmação de compra.

**cliente:** é o pedido 7

<sub>🔧 lookup_order(order_id=7) · search_policies(question='telefone WhatsApp contato da loja')</sub>

**Dani:** Achei o pedido #7 aqui, e infelizmente o arrependimento não vale mais para ele. Ele foi entregue em 17/02, há 34 dias, e o prazo de 7 dias corridos já passou.

Mesmo assim, ele ainda está coberto pela garantia legal de 90 dias contra defeito de fabricação, que vai até cerca de 18/05. Ou seja, se a Shelby SU-21S apresentar algum defeito de fábrica, dá para acionar a troca ou o conserto por aí. Arrependimento sem defeito, porém, não se enquadra.

Se quiser conversar com a equipe sobre a sua situação, o contato é (67) 3341-4444, pelo WhatsApp ou telefone, de segunda a sexta das 9h às 18h e sábado das 9h às 13h. Eles podem olhar o caso com você.

Ficou mais alguma dúvida?

**cliente:** e se for defeito de fábrica, muda alguma coisa?

<sub>🔧 search_policies(question='defeito de fabricação troca garantia')</sub>

**Dani:** Sim, muda bastante, mas o caminho é outro. A troca direta na loja por defeito vale só nos primeiros 30 dias após a compra, e o pedido #7 já passou desse prazo (a compra foi em 03/02).

Depois disso, a garantia legal de 90 dias contados do recebimento (que vai até cerca de 18/05 no seu caso) cobre defeito de fabricação. Nesse período, você aciona a garantia com a gente: a loja pode intermediar o processo com o fabricante a seu pedido. Também vale checar o certificado de garantia que veio com a Shelby, porque muitos fabricantes têm garantia própria, de 6 meses a 2 anos, que pode estar valendo além disso.

Ficam de fora danos por mau uso, quedas, umidade excessiva ou modificações não autorizadas.

Se você estiver com um defeito, o melhor é chamar a equipe no (67) 3341-4444, WhatsApp ou telefone, de seg a sex das 9h às 18h e sábado das 9h às 13h. Eles vão olhar o caso e te dizer os próximos passos. Quer que eu ajude com mais alguma coisa?
