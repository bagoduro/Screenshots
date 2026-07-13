sudo masscan -p 37777 179.126.0.0-179.126.255.255 --rate 5000 -oL ~/Screenshots/ips.txt -e ens5


grep 'open tcp 37777' ~/Screenshots/ips.txt | awk '{print $4}' > ~/Screenshots/ips37777.txt

# Com a lista padrão ips.txt e porta 80
python3 screenshots.py

# Com um arquivo específico e porta 80
python3 screenshots.py -f formatado.txt -p 500

# Com porta diferente (ex: 37777)
python3 screenshots.py -f ips.txt -p 37777
