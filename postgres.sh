#!/usr/bin/env bash

startTime=${SECONDS}

# Starting point of this script
function run(){

    pushd "${PROJECT_ROOT}/D:/ROC_db_generate" > /dev/null
    echo ""
    read -p "Do you want to pull from gsheet to generate sql in MSSQL (y/n) : " PULL
    read -p "Do you want to run as (dev/prod) : " ENV
    if [ "$PULL" == "y" ]
    then

        echo ""
        echo "--------------------------- MSSQL(Start) ---------------------------"
        ./sql-script-generator.py $ENV
        echo "--------------------------- MSSQL(Stop) ----------------------------"
    fi

    flyway clean migrate

    if [ "$?" != "0" ]
    then
        echo "ERROR found during flyway"
        popd > /dev/null
        exit -1
    fi

    echo ""
    echo "Postgres (Flyway) complete"

    popd > /dev/null

}

run

endTime=${SECONDS}
diffTime=`expr ${endTime} - ${startTime}`
printf '\033[93mPostgres sql generate time \033[1m %02d:%02d:%02d \033[0m\n' $(($diffTime/3600)) $(($diffTime%3600/60)) $(($diffTime%60))
