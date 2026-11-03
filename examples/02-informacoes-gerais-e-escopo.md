# Informações da loja e pedido fora do catálogo

Endereço e horário saem do manual de políticas. Em seguida o cliente pede acessórios, que a loja não comercializa — o agente redireciona sem inventar um produto.

> Gerado por `scripts/generate_examples.py` · modelo `claude-haiku-5-5` · data de referência do agente: 2026-03-23

---

**cliente:** qual o endereço da loja?

<sub>🔧 search_policies(question='endereço da loja')</sub>

**Dani:** A loja fica na Rua 14 de Maio, 3200, Centro, Campo Grande - MS, CEP 79202-333.

Se precisar, o WhatsApp e telefone é (67) 3341-4444. Quer mais alguma coisa?

**cliente:** vocês abrem sábado que horas?

<sub>🔧 search_policies(question='horário de funcionamento sábado')</sub>

**Dani:** No sábado a loja atende das 9h às 13h. Durante a semana, é de segunda a sexta, das 9h às 18h. Domingo e feriados ficam fechados.

Ficou mais alguma dúvida?

**cliente:** preciso de um jogo de cordas e umas palhetas também, tem?

**Dani:** Cordas e palhetas são acessórios, e a Empório da Música trabalha só com instrumentos musicais, então infelizmente não temos isso aqui.

Se quiser, posso procurar algum instrumento para você, como violão, guitarra, baixo ou teclado. Tem algo em mente?
