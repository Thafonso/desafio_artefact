# Pergunta fora de escopo e rastreio de pedido

Pergunta sem relação com a loja é recusada com leveza. Na sequência, um pedido já despachado e outro ainda sem rastreio — o agente explica a diferença em vez de inventar um código.

> Gerado por `scripts/generate_examples.py` · modelo `claude-haiku-5-5` · data de referência do agente: 2026-03-23

---

**cliente:** qual a capital da Mongólia?

**Dani:** Essa eu não consigo ajudar, sou do atendimento da Empório da Música e só cuido de instrumentos e das coisas da loja. Se estiver procurando algum instrumento, violão, guitarra, teclado ou outro, é só me falar!

**cliente:** haha beleza. cadê meu pedido 8?

<sub>🔧 lookup_order(order_id=8) · search_policies(question='telefone WhatsApp contato atendimento')</sub>

**Dani:** Pelo que aparece aqui, o pedido #8 já foi enviado (Kala KA-C Concert Mogno), com rastreio BRJL5544332BR. Mas a previsão de entrega era 28/02, e ele ainda não consta como entregue. Ou seja, está atrasado há cerca de três semanas.

Não consigo ver onde o pacote está agora, então o melhor é a equipe verificar com a transportadora. O canal de WhatsApp de atendimento é o (67) 3321-4500. No cadastro da empresa aparece também o (67) 3341-4444 como telefone/WhatsApp, então, se um não responder, tente o outro. Tenha em mãos o número do pedido e o código de rastreio.

Se o pacote não aparecer, a equipe vai te orientar sobre os próximos passos. Ficou alguma dúvida?

**cliente:** e o pedido 13, que tá demorando?

<sub>🔧 lookup_order(order_id=13)</sub>

**Dani:** O pedido #13 (Ohana BK-35E Barítono Elétrico Natural, R$ 1.899,00, pago via PIX) está aguardando pagamento. Ele ainda não foi despachado, por isso não tem código de rastreio. O rastreio é enviado por e-mail e WhatsApp assim que o pedido sai.

Se você ainda não pagou, a demora é por isso e é preciso concluir o pagamento. Se você já pagou por PIX, fale com a equipe para confirmar o recebimento: (67) 3321-4500 ou (67) 3341-4444. Tenha o número do pedido em mãos.

Ficou alguma dúvida?
