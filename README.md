docker build -t hac-crawler .
docker run -d --name hac-crawler --env-file .env hac-crawler
docker exec -it hac-crawler /bin/bash
python main.py

#Add this css to wordpress theme:
.chord {
    color: red;
    font-weight: bold;
}
