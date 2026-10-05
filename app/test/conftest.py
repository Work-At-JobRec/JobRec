def pytest_addoption(parser):
    parser.addoption(
        "--run-openai",
        action="store_true",
        default=False,
        help="Run tests that connect to the OpenAI API"
    )