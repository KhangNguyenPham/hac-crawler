docker build -t hac-crawler .
docker run -d --name hac-crawler --env-file .env hac-crawler
docker exec -it hac-crawler /bin/bash
python main.py

#Add this css to wordpress theme:
.chord {
    color: red;
    font-weight: bold;
}

#Rebuild
docker cp hac-crawler:/app/cache ./cache_backup
docker stop hac-crawler
docker rm hac-crawler
docker build -t hac-crawler .
docker run -d --name hac-crawler --env-file .env -v $(pwd)/cache_backup:/app/cache hac-crawler
python main.py
