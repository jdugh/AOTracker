#!/usr/bin/python3 
# -*- coding: utf-8 -*-
##################################################
## Web Interface for BOAMP
##################################################
from flask import Flask, render_template, request, jsonify
from database import TrackerDatabase
from datetime import datetime, timedelta

app = Flask(__name__)
db = TrackerDatabase()

@app.route('/')
def index():
    """Page principale"""
    stats = db.get_stats()
    return render_template('index.html', stats=stats)

@app.route('/api/appels_offre')
def get_appels_offre():
    """API pour récupérer les AO (avec filtres optionnels)"""
    filtre = request.args.get('statut', None)
    aos = db.get_all(filtre_statut=filtre)
    
    # Ajouter les indicateurs de couleur
    for ao in aos:
        ao['urgence'] = get_urgence_level(ao['deadline'])
        ao['is_new'] = is_new_ao(ao['date_parution'])
    
    return jsonify(aos)

@app.route('/api/update_statut', methods=['POST'])
def update_statut():
    """API pour mettre à jour le statut d'un AO"""
    data = request.json
    reference = data.get('reference')
    statut = data.get('statut')
    
    if not reference or not statut:
        return jsonify({'error': 'Missing parameters'}), 400
    
    db.update_statut(reference, statut)
    return jsonify({'success': True})

@app.route('/api/update_commentaire', methods=['POST'])
def update_commentaire():
    """API pour mettre à jour le commentaire d'un AO"""
    data = request.json
    reference = data.get('reference')
    commentaire = data.get('commentaire', '')
    
    if not reference:
        return jsonify({'error': 'Missing reference'}), 400
    
    db.update_commentaire(reference, commentaire)
    return jsonify({'success': True})

@app.route('/api/stats')
def get_stats():
    """API pour récupérer les statistiques"""
    return jsonify(db.get_stats())

def get_urgence_level(deadline_str):
    """Détermine le niveau d'urgence (rouge/jaune/vert)"""
    if deadline_str == 'N/C':
        return 'unknown'
    
    try:
        deadline = datetime.strptime(deadline_str, '%Y-%m-%d %H:%M:%S')
        now = datetime.now()
        diff = (deadline - now).days
        
        if diff < 10:
            return 'red'
        elif diff < 20:
            return 'yellow'
        else:
            return 'green'
    except:
        return 'unknown'

def is_new_ao(date_parution_str):
    """Vérifie si l'AO est nouveau (< 3 jours)"""
    if date_parution_str == 'N/C':
        return False
    
    try:
        date_parution = datetime.strptime(date_parution_str, '%Y-%m-%d %H:%M:%S')
        now = datetime.now()
        return (now - date_parution).days < 3
    except:
        return False

if __name__ == '__main__':
    print("🚀 Démarrage du serveur web BOAMP...")
    print("📱 Accédez à l'interface : http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
