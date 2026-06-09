#!/usr/bin/python3 
# -*- coding: utf-8 -*-
##################################################
## Web Interface for BOAMP
##################################################
from flask import Flask, render_template, request, jsonify
from database import TrackerDatabase
from datetime import datetime, timedelta
from pathlib import Path
import json
import re

app = Flask(__name__)
db = TrackerDatabase()
PLACE_SUMMARY_ROOT = Path('dce_storage') / 'place'

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


@app.route('/api/ao_summary/<reference>')
def get_ao_summary(reference):
    """API pour récupérer le contenu summary.json d'un AO PLACE."""
    if not re.match(r'^[A-Za-z0-9_-]+$', reference):
        return jsonify({'error': 'Invalid reference'}), 400

    ao = db.get_by_reference(reference)
    if not ao:
        return jsonify({'success': False, 'exists': False, 'message': 'AO introuvable'}), 404

    summary_path = None
    local_path = (ao.get('dce_local_path') or '').strip()
    if local_path:
        candidate = Path(local_path) / 'summary.json'
        if candidate.exists() and candidate.is_file():
            summary_path = candidate

    if summary_path is None:
        fallback = PLACE_SUMMARY_ROOT / reference / 'summary.json'
        if fallback.exists() and fallback.is_file():
            summary_path = fallback

    if summary_path is None:
        return jsonify({
            'success': True,
            'exists': False,
            'message': 'summary.json non disponible pour cet AO'
        })

    try:
        with summary_path.open('r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return jsonify({'success': False, 'exists': False, 'message': 'summary.json invalide'}), 500

    return jsonify({
        'success': True,
        'exists': True,
        'reference': reference,
        'markdown_summary': data.get('markdown_summary', ''),
        'structured_output': data.get('structured_output', {}),
    })

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
