__version__ = "0.1"

__all__ = ["ResumeGenerator", "StyleManager", "ResumeFacade"]


def __getattr__(name):
    """
    Lazy-import package exports to avoid importing heavy dependencies
    when only submodules are needed (e.g. llm_job_parser).
    """
    if name == "ResumeGenerator":
        from .resume_generator import ResumeGenerator
        return ResumeGenerator
    if name == "StyleManager":
        from .style_manager import StyleManager
        return StyleManager
    if name == "ResumeFacade":
        from .resume_facade import ResumeFacade
        return ResumeFacade
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
