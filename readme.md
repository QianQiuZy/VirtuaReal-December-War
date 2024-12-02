# VirtuaReal December War

This application is a simple Flask web server that fetches ranking and user information from VirtuaReal December War and serves it through a web interface.

## Table of Contents

- [Installation](#installation)
- [Usage](#usage)
- [API Endpoints](#api-endpoints)
- [License](#license)

## Installation

To get the application running on your local machine, follow these steps:

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/bilibili-ranking-app.git
   cd bilibili-ranking-app
   ```

2. **Create a virtual environment (optional but recommended):**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install the dependencies:**
   ```bash
   pip install Flask requests
   ```

## Usage

Once the installation is complete, you can start the Flask application:

```bash
python app.py
```

The application will start running on `http://localhost:2992` by default. You can access the web interface and API endpoints from there.

## API Endpoints

- **Root Endpoint:**
  `GET /` - Returns the rendered HTML template of the VR page.

- **Ranking Data Endpoint:**
  `GET /get_ranking` - Returns the ranking data in JSON format.

- **Avatar Endpoint:**
  `GET /avatar/<url>` - Returns the avatar image from the provided URL.
