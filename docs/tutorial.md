# Tutorial JobRec

## Overview

JobRec is a web application designed to give you relevant job recommendations based on your resume. You will upload your resume, then browse through different relevant recommended jobs. If you like, you can select one of the recommended jobs to be redirected to the application where you can apply for that job.

## Prerequisites

- You will need a valid email address in order to create an account.
- You will also need a resume to upload, to populate your recommendations.
  - If you are not comfortable with uploading your resume, you can test out JobRec with the sample resume [`test_resume.pdf`](https://github.com/Work-At-JobRec/JobRec/blob/main/uploads/test_resume.pdf) in the `uploads` folder.

## Setup / Installation

1. Open [https://jobrec.thecoolsite.org/](https://jobrec.thecoolsite.org/) in your browser.
2. Select the **Log In** button in the top right corner.
3. Click **Sign Up**.
4. Clicking **Continue with Google** or **Continue with GitHub** will use your Google or GitHub account to sign in. If you don't want that, type your email address in the **Email Address** field and click **Continue**.
5. You can create a passkey or use a password. To use a password, click **Continue without passkeys**.
6. Enter your password, which should be at least 15 characters, and click **Continue**.
7. You should now have an account.

## First Workflow

1. Click the **Profile** button at the top.
2. Fill in the required information to continue, or click **Skip**.
3. Click **Choose resume** to select your resume file.
4. Click **Upload & Parse**, and wait for your profile to populate.
5. After your profile is populated, click **Jobs**.
6. Browse through the job recommendations and find a job you are interested in.
7. Select the job to browse its information. Click **Apply Now** if you want to be redirected to the external site where you can apply.

## Expected Results

- Your profile should be populated with the skills detected from your resume.
- The job listings should display a compatibility percentage based on how well each listing matches your skills.
- You should be able to click **Apply Now** to be redirected to an external application site.

## Troubleshooting

If something does not work, please create an issue on our [GitHub Issues page](https://github.com/Work-At-JobRec/JobRec/issues). There is a standard template for reporting bugs.
