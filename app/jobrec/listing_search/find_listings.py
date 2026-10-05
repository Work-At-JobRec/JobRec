def get_job_recommendations(
    user_id: str,
    page: int | None,
    salary_low: int | None,
    salary_high: int | None,
    radius: int | None,
    position_type: list[str] | None,
    location_override: str | None,
    position_name: str | None,
    company_name: str | None,
):
    raise NotImplementedError


def find_skill_gaps(user_id: str, listing_id: str):
    # TODO: given a user and a listing, identify the skill gaps the user has
    raise NotImplementedError


def find_percentile(user_id: str, listing_id: str):
    # TODO: given a user and a listing, estimate the percentage of candidates the user exceeds in qualifications
    raise NotImplementedError
