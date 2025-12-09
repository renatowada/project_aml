import pandas as pd
import random
import argparse
import os
import unicodedata
from faker import Faker
from datetime import datetime, timedelta

# Configurações de reprodutibilidade
Faker.seed(42)
fake = Faker('pt_BR')

# Pesos de categorias
cat_cols = {
    'gender': {'options': ['m', 'f'], 'weight': [0.5, 0.5]},
    'account_type': {'options': ['corrente', 'poupanca', 'salario', 'pagamento'], 'weight': [0.4, 0.2, 0.2, 0.2]},
    'transaction_type': {'options': ['pix', 'ted', 'boleto'], 'weight': [0.7, 0.1, 0.2]},
    'device': {'options': ['cellphone', 'desktop'], 'weight': [0.8, 0.2]},
    'receiver_acc_type': {'options': ['corrente', 'poupanca', 'salario', 'pagamento'], 'weight': [0.4, 0.2, 0.2, 0.2]},
    'device_os': {'options': ['myos', 'bot', 'bluescreen', 'cheeseos', 'penguin'], 'weight': [0.2, 0.5, 0.1, 0.1, 0.1]}
}

def remove_acentos(texto):
    if isinstance(texto, str):
        texto = unicodedata.normalize('NFKD', texto)
        texto = texto.encode('ascii', 'ignore').decode('utf-8')
    return texto

def generate_synthetic_data(num_rows=100000):
    
    random.seed(42)
    rng = random.Random(42)
    
    # 1. Gerar Contas
    num_unique_accounts = int(num_rows * 0.45)
    accounts_db = {}
    all_account_ids = []

    for i in range(num_unique_accounts):
        acc_id = f"acc{i:06d}"
        all_account_ids.append(acc_id)
        
        creation_date = fake.date_between(start_date='-5y', end_date='today')

        age_group = rng.choices(['young', 'adult', 'mid', 'senior'], weights=[0.20, 0.45, 0.25, 0.10])[0]

        if age_group == 'young':
            birth_date = fake.date_of_birth(minimum_age=18, maximum_age=25)
        elif age_group == 'adult':
            birth_date = fake.date_of_birth(minimum_age=26, maximum_age=45)
        elif age_group == 'mid':
            birth_date = fake.date_of_birth(minimum_age=46, maximum_age=60)
        else:
            birth_date = fake.date_of_birth(minimum_age=61, maximum_age=90)

        raw_score = int(rng.gauss(600, 150))
        credit_score = max(300, min(850, raw_score))

        accounts_db[acc_id] = {
            'name': remove_acentos(fake.name()),
            'cpf': fake.cpf(),
            'birth_date': birth_date,
            'address_pcode': fake.postcode(),
            'phone_number': fake.phone_number(),
            'acc_creation_date': creation_date,
            'agency': fake.random_number(digits=4),
            'account': fake.random_number(digits=6),
            'credit_score': credit_score,
            'device_id': fake.bothify(text="dv##"),
            'device_model': fake.bothify(text="md##"),
        }

    # 2. Definir Papéis (Fraude vs Honesto)
    rng.shuffle(all_account_ids)
    n_mules = int(len(all_account_ids) * 0.05) # 5% Laranjas
    n_bosses = int(len(all_account_ids) * 0.01) # 1% Chefes
    
    mules_pool = all_account_ids[:n_mules]
    bosses_pool = all_account_ids[n_mules : n_mules + n_bosses]
    honest_pool = all_account_ids[n_mules + n_bosses:] # O resto é honesto

    print(f"Laranjas: {len(mules_pool)} | Chefes: {len(bosses_pool)} | Honestos: {len(honest_pool)}")

    # 3. Gerar Transações
    data = []
    
    # Loop de geração
    current_row = 0
    while current_row < num_rows:
        
        # Sorteio do Cenário
        # normal: 80% | fraude: 10% | ruído: 10%
        scenario = rng.choices(['normal', 'fraud_cycle', 'noise'], weights=[0.80, 0.10, 0.10], k=1)[0]
        
        rows_to_add = []
        
        # --- CENÁRIO 1: Transação Normal ---
        if scenario == 'normal':
            sender = rng.choice(all_account_ids)
            receiver = rng.choice(all_account_ids)
            while receiver == sender: receiver = rng.choice(all_account_ids)
            
            amount = round(rng.uniform(10, 2500), 2)
            date = fake.date_time_between(start_date='-90d', end_date="now")
            
            rows_to_add.append({
                'sender_id': sender, 'receiver_id': receiver, 
                'transaction_amount': amount, 'transaction_time': date, 'type': 'pix'
            })
            
        # --- CENÁRIO 2: Fraude (Laranja) ---
        elif scenario == 'fraud_cycle':
            mule = rng.choice(mules_pool)
            boss = rng.choice(bosses_pool)
            victim = rng.choice(honest_pool) # Dinheiro vem de uma vitima ou conta invadida
            
            base_amount = round(rng.uniform(1000, 50000), 2)
            date_in = fake.date_time_between(start_date='-90d', end_date="-5d")
            
            # 2a. Entrada (Vítima -> Laranja)
            rows_to_add.append({
                'sender_id': victim, 'receiver_id': mule, 
                'transaction_amount': base_amount, 'transaction_time': date_in, 'type': 'pix'
            })
            
            # 2b. Saída (Laranja -> Chefe)
            # RUÍDO: Variar taxa (1% a 30%) e tempo (minutos a dias)
            fee = rng.uniform(0.01, 0.30)
            amount_out = round(base_amount * (1 - fee), 2)
            
            if rng.random() < 0.2: 
                delay = timedelta(days=rng.randint(1, 4)) # Laranja demorado
            else:
                delay = timedelta(minutes=rng.randint(10, 300)) # Laranja rápido
                
            rows_to_add.append({
                'sender_id': mule, 'receiver_id': boss, 
                'transaction_amount': amount_out, 'transaction_time': date_in + delay, 'type': 'pix'
            })

        # --- CENÁRIO 3: RUÍDO ---
        # Honesto recebe muito e gasta quase tudo rápido 
        # Sem isso o dataset fica muito simples e o modelo decora os padrões
        elif scenario == 'noise':
            company = rng.choice(all_account_ids)
            honest_worker = rng.choice(honest_pool)
            
            salary = round(rng.uniform(2500, 15000), 2)
            date_in = fake.date_time_between(start_date='-90d', end_date="-5d")
            
            # 3a. Recebe Salário
            rows_to_add.append({
                'sender_id': company, 'receiver_id': honest_worker, 
                'transaction_amount': salary, 'transaction_time': date_in, 'type': 'ted'
            })
            
            # 3b. Paga Contas / Investe (Saída Rápida e Alta)
            # Repassa 90-99% do valor
            pct_spent = rng.uniform(0.90, 0.99)
            amount_out = round(salary * pct_spent, 2)
            delay = timedelta(minutes=rng.randint(5, 400)) # Rápido igual laranja
            
            bill_receiver = rng.choice(all_account_ids)
            
            rows_to_add.append({
                'sender_id': honest_worker, 'receiver_id': bill_receiver, 
                'transaction_amount': amount_out, 'transaction_time': date_in + delay, 'type': 'boleto'
            })

        # Processar as linhas criadas
        for r in rows_to_add:
            # Preenche com dados cadastrais (Fixos)
            sender_prof = accounts_db[r['sender_id']]
            rec_prof = accounts_db[r['receiver_id']]
            
            full_row = {
                'transaction_id': current_row,
                'transaction_amount': r['transaction_amount'],
                'transaction_time': r['transaction_time'],
                'sender_id': r['sender_id'],
                'receiver_id': r['receiver_id'],
                'transaction_type': r.get('type', 'pix'),
                'transaction_city': remove_acentos(fake.city()),
                # Dados Sender
                'name': sender_prof['name'], 'cpf': sender_prof['cpf'],
                'birth_date': sender_prof['birth_date'], 'address_pcode': sender_prof['address_pcode'],
                'phone_number': sender_prof['phone_number'], 'acc_creation_date': sender_prof['acc_creation_date'],
                'agency': sender_prof['agency'], 'account': sender_prof['account'],
                'credit_score': sender_prof['credit_score'], 'device_id': sender_prof['device_id'], 'device_model': sender_prof['device_model'],
                # Dados Receiver
                'receiver_name': rec_prof['name'], 'receiver_bank': fake.bothify("bk##"),
                'receiver_agency': rec_prof['agency'], 'receiver_account': rec_prof['account']
            }
            
            # Preencher categóricas faltantes
            for col, info in cat_cols.items():
                if col not in full_row:
                    full_row[col] = rng.choices(info['options'], weights=info['weight'], k=1)[0]
            
            data.append(full_row)
            current_row += 1

    # 4. Criar Dataframes Finais
    df = pd.DataFrame(data)
    
    labels_data = []
    for acc in all_account_ids:
        label = 0
        role = 'Honest'
        if acc in mules_pool:
            label = 1
            role = 'Mule'
        elif acc in bosses_pool:
            label = 1
            role = 'Boss'
        labels_data.append({'account_id': acc, 'is_fraud': label, 'role': role})
        
    df_labels = pd.DataFrame(labels_data)
    
    # Reordenar colunas
    cols_order = ['transaction_id', 'transaction_time', 'transaction_amount', 'sender_id', 'receiver_id'] + \
                 [c for c in df.columns if c not in ['transaction_id', 'transaction_time', 'transaction_amount', 'sender_id', 'receiver_id']]
    
    return df[cols_order], df_labels

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=100000)
    args = parser.parse_args()

    df_trans, df_lab = generate_synthetic_data(num_rows=args.rows)

    # Caminhos
    script_dir = os.path.dirname(os.path.abspath(__file__))

    project_root = os.path.dirname(os.path.dirname(script_dir)) 

    try:
        out_data = os.path.join(project_root, 'data', '01_raw', 'synthetic_dataset.csv')
        out_lbl = os.path.join(project_root, 'data', '01_raw', 'accounts_labels.csv')
        os.makedirs(os.path.dirname(out_data), exist_ok=True)
    except:
        out_data = 'synthetic_dataset.csv'
        out_lbl = 'accounts_labels.csv'

    df_trans.to_csv(out_data, index=False)
    df_lab.to_csv(out_lbl, index=False)
