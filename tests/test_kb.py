from app.kb import KnowledgeBase, parse_article

kb = KnowledgeBase()


def test_all_articles_parse_with_steps():
    assert 10 <= len(kb.articles) <= 20
    for a in kb.articles:
        assert a.id and a.title and a.category
        assert len(a.steps) >= 4, a.id
        assert a.next_action, a.id


def test_article_ids_and_categories_unique():
    assert len({a.id for a in kb.articles}) == len(kb.articles)
    assert len({a.category for a in kb.articles}) == len(kb.articles)


def test_parse_article_front_matter():
    a = parse_article("---\nid: x\ntitle: X\ncategory: c\nkeywords: a, b\n---\n# X\n\n"
                      "## Troubleshooting Steps\n1. One\n2. Two\n\n## When to Escalate\n- Hmm\n\n"
                      "## Recommended Next Action\nCall IT.\n")
    assert a.steps == ["One", "Two"] and a.keywords == ["a", "b"]
    assert a.escalate_when == ["Hmm"] and a.next_action == "Call IT."


def test_retrieval_ranks_relevant_article_first():
    cases = {
        "paper jam in the printer": "printer",
        "wifi keeps disconnecting": "network",
        "outlook not receiving emails": "email",
        "blue screen with stop code": "bsod",
        "my account is locked after password attempts": "account",
        "vpn won't connect from home": "vpn",
    }
    for query, category in cases.items():
        assert kb.search(query)[0][0].category == category, query


def test_search_empty_query():
    assert kb.search("") == []
