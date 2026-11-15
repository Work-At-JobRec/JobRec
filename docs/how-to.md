# How to Use JobRec for End Users

## How to report listings

Sometimes, job listings will be inaccurate or harmful, and they should be reported when one is observed.

### Steps
1. Navigate to the job through the recommendation feed or your bookmarks
2. click the `report` button in the top right corner of the job
3. Fill out information regarding the issue with this listing
4. Click "submit." The job should be automatically hidden from your feed, and the report will be stored on the server for maintainers to review

## How to Edit your Information

When you change careers or engage in large projects, you may wish to change your skills, education level, or other information.

### Steps
1. Log into JobRec, and navigate to your profile
2. On the right panel, locate the field you want to update
3. If you wish to add an entry, click the "plus" button at the top of the field and fill out your new information
4. If you wish to remove an entry, click the "X" button next to the item you want to remove
5. Your recommendations should now be updated to match this new information

## How to Filter your Search

Recommendations may not account for all of your preferences, such as salary and location. You can use filters to correct that.

### Steps
1. Navigate to the "Search" tab
2. Open the "Filters dropdown"
3. Modify your desired location, salary, position type, position name, and company
4. Press search again. Recommendations should now match your preferences.

## How to change your password

If you forget your password, JobRec will not allow you to log in. Auth0 allows you to reset your password through a recovery email for this purpose

### Steps
1. (If logged in) log out of JobRec
2. Click the "Log In" button in the header
3. Navigate to the link which says "Can't log in to your account?"
4. Enter you email address, then wait for an email from Auth0.
5. Follow the instructions in the email to reset your password
6. Log into JobRec again.

# How to Use JobRec for Developers and Deployers

## How to run this repository locally

If you're making modifications to the codebase for the sake of future improvements, you will likely want to run the repository locally to check your changes. Here's how you would go about setting up a local development server:

### Prerequisites

To run JobRec, you will need to install python, [poetry](https://pypi.org/project/poetry/), and NodeJS. You will also need an auth0 application + API, as well as an OpenAI-compatible API key.

### Steps
1. create a `.env` file based on the `.env.example` file in the root of the JobRec repository.
2. Navigate to the `app` directory and run `poetry install`. This will install all required dependencies for JobRec's backend
3. Once installation is complete, use `poetry run python -m jobrec.app` to run the backend on the hostname and port specified in the `.env` file.
4. Next, navigate to the `frontend/` directory and run `npm install`. This will install all required dependencies for JobRec's frontend
5. To run the frontend on a development server, use `npx vite`.
6. Navigate to `http://localhost:5173` to see the JobRec frontend.
7. Finally, if you want to test any periodic actions:
    - **Listing Scraping:** Use `poetry run python -m jobrec.scrape_all`
    - **Skill Extraction:** Use `poetry run python -m jobrec.listing_skill_extractor`
    - **Listing Pruning:** Use `poetry run python -m jobrec.prune_jobs`

## How to Deploy this repository

If you want to host your changes publically, you will want to deploy this repository to AWS.

### Prerequisites

You will need an AWS account with an IAM role that allows GitHub actions to access your compute node. You can find instructions for how to configure that [here](https://aws.amazon.com/blogs/security/use-iam-roles-to-connect-github-actions-to-actions-in-aws/). In addition, you will need a secret stored in AWS secrets manager that has all of the values listed in `.env.example`, and you will need a private key that allows SSH access into the worker instance. For authentication to work, you will also need to have SSL set up for the domain you host JobRec on. Finally, your compute node will need to be running amazon linux or another OS which uses dnf for package management.

### Steps
1. Fork this repository
2. Add the following secrets to the repository:
    - `LIGHTSAIL_IP`: IP address of the intended deployment
    - `LIGHTSAIL_USER`: The linux user which will run JobRec
    - `LIGHTSAIL_PEM_KEY`: The private key used to SSH into the worker node
    - `SSL_FULLCHAIN`: The fullchain key of the SSL certificate used by JobRec
    - `SSL_PRIVATE`: The private key of the SSL certificate used by JobRec
3. Run the `deploy-to-aws` GitHub action
4. Ensure your worker node has firewall access to the outside web over both ipv4 and ipv6.
5. Finally, visit the configured domain and observe functionality.

## How to Scrape Jobs

Scraping jobs locally is an important part of testing the application, including improvements to job matching and listing displays.

### Prerequisites

Be familiar with the content in [How Do I Run the Repository Locally?](##-How-to-run-this-repository-locally)

### Steps
1. Configure sources for scraping in `app/jobrec/job_sources.json`
    - Each entry contains a company ID and a job board type, as well as an enable/disable flag. Future updates will also allow you to scrape all listings on a specific platform instead of filtering by company.
2. Set `DATABASE_URL` to the database you want to scrape listings into
3. Run `poetry run python -m jobrec.scrape_all`

## How to Run OpenAI-related Tests

tests which utilise the OpenAI API are excluded from CI runs by default due to their long execution times and potential for heavy token usage. These tests should be run locally instead

### Steps
1. Configure an OpenAI API key with sufficient tokens for each required test
2. In `app/`, run `pytest /Tests --run-openai`
3. Don't be alarmed if this process takes longer than 15 minutes; API response times are heavily variable and much longer than compute times for this application.