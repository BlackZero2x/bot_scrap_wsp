ALTER TABLE dbo.fija_data_toa ADD
    [toa_uso_cable_coaxial_en_acometida_1014] NVARCHAR(5) NULL,  -- 1014: Uso cable coaxial en acometida
    [toa_id_de_acceso_voz_para_la_activacion_1057] NVARCHAR(100) NULL,  -- 1057: ID de Acceso Voz para la Activación
    [toa_id_de_acceso_baf_para_la_activacion_1060] NVARCHAR(50) NULL,  -- 1060: ID de Acceso BAF para la Activación
    [toa_id_de_acceso_tv_para_la_activacion_1067] NVARCHAR(50) NULL,  -- 1067: ID de Acceso TV para la Activación
    [toa_desea_la_instalacion_de_repetidor_1227] NVARCHAR(255) NULL,  -- 1227: Desea la instalación de repetidor ?
    [toa_numero_de_puntos_adicionales_cableado_1232] NVARCHAR(255) NULL,  -- 1232: Número de Puntos Adicionales(Cableado)
    [toa_orden_de_servicio_137] NVARCHAR(50) NULL,  -- 137: Orden de Servicio
    [toa_puntos_adicionales_cableado_1600] NVARCHAR(255) NULL,  -- 1600: Puntos Adicionales(Cableado)
    [toa_cableado_01_mts_1601] NVARCHAR(255) NULL,  -- 1601: Cableado 01 MTS
    [toa_cableado_02_mts_1602] NVARCHAR(255) NULL,  -- 1602: Cableado 02 MTS
    [toa_cableado_03_mts_1603] NVARCHAR(255) NULL,  -- 1603: Cableado 03 MTS
    [toa_cableado_04_mts_1604] NVARCHAR(255) NULL,  -- 1604: Cableado 04 MTS
    [toa_cableado_05_mts_1605] NVARCHAR(255) NULL,  -- 1605: Cableado 05 MTS
    [toa_cableado_06_mts_1606] NVARCHAR(255) NULL,  -- 1606: Cableado 06 MTS
    [toa_cableado_07_mts_1607] NVARCHAR(255) NULL,  -- 1607: Cableado 07 MTS
    [toa_estado_de_soporte_de_planta_101_1628] NVARCHAR(100) NULL,  -- 1628: Estado de Soporte de Planta 101
    [toa_numero_de_intentos_del_soporte_de_101_1631] NVARCHAR(100) NULL,  -- 1631: Número de intentos del soporte de 101
    [toa_observacion_soporte_de_planta_101_1633] NVARCHAR(100) NULL,  -- 1633: Observación Soporte de Planta 101
    [toa_foto_evidencia_02_1658] NVARCHAR(255) NULL,  -- 1658: Foto Evidencia 02
    [toa_sub_motivo_de_soporte_de_planta_101_1661] NVARCHAR(255) NULL,  -- 1661: Sub Motivo de Soporte de Planta 101
    [toa_foto_realizar_zoom_a_la_firma_y_dni_de_la_boleta_firmada_por_el_cliente_1684] NVARCHAR(255) NULL,  -- 1684: Foto realizar Zoom a la Firma y DNI de la boleta firmada por el Cliente
    [toa_indicador_form_conformidad_1686] NVARCHAR(5) NULL,  -- 1686: Indicador Form. Conformidad
    [toa_indicador_recurso_linea_de_rescate_1962] NVARCHAR(255) NULL,  -- 1962: Indicador Recurso Línea de Rescate
    [toa_foto_de_roseta_sin_tapa_1985] NVARCHAR(255) NULL,  -- 1985: Foto de Roseta (sin tapa)
    [toa_foto_de_triplexor_1986] NVARCHAR(255) NULL,  -- 1986: Foto de Triplexor
    [toa_foto_de_hgu_roseta_libre_de_obstaculos_1987] NVARCHAR(255) NULL,  -- 1987: Foto de HGU + Roseta (libre de obstaculos)
    [toa_foto_de_1er_splitter_filtro_retorno_1988] NVARCHAR(255) NULL,  -- 1988: Foto de 1er Splitter + Filtro retorno
    [toa_foto_de_cablemodem_libre_de_obstaculos_1989] NVARCHAR(255) NULL,  -- 1989: Foto de CABLEMODEM (libre de obstáculos)
    [toa_foto_de_hgu_triplexor_libre_de_obstaculos_1990] NVARCHAR(255) NULL,  -- 1990: Foto de HGU + Triplexor (libre de obstáculos)
    [toa_nombre_persona_que_recibe_204] NVARCHAR(100) NULL,  -- 204: Nombre Persona que Recibe
    [toa_dni_persona_que_recibe_205] NVARCHAR(50) NULL,  -- 205: DNI Persona que Recibe
    [toa_motivo_de_suspension_214] NVARCHAR(255) NULL,  -- 214: Motivo de suspensión
    [toa_boleta_de_reparacion_225] NVARCHAR(255) NULL,  -- 225: Boleta de Reparación
    [toa_codigo_de_requerimiento_234] NVARCHAR(255) NULL,  -- 234: Código de Requerimiento
    [toa_gestion_2372] NVARCHAR(255) NULL,  -- 2372: Gestion
    [toa_fotografia_boleta_de_cierre_238] NVARCHAR(255) NULL,  -- 238: Fotografía Boleta de Cierre
    [toa_fotofragia_adicional_1_239] NVARCHAR(255) NULL,  -- 239: Fotofragía adicional 1
    [toa_fotografia_adicional_2_240] NVARCHAR(255) NULL,  -- 240: Fotografía adicional 2
    [toa_fotografia_adicional_3_241] NVARCHAR(255) NULL,  -- 241: Fotografía adicional 3
    [toa_fotografia_adicional_4_242] NVARCHAR(255) NULL,  -- 242: Fotografía adicional 4
    [toa_fotografia_adicional_5_243] NVARCHAR(255) NULL,  -- 243: Fotografía adicional 5
    [toa_fotografia_adicional_6_244] NVARCHAR(255) NULL,  -- 244: Fotografía adicional 6
    [toa_fotografia_adicional_7_245] NVARCHAR(255) NULL,  -- 245: Fotografía adicional 7
    [toa_motivo_liquidacion_instalacion_247] NVARCHAR(100) NULL,  -- 247: Motivo liquidación instalación
    [toa_telefono_contacto_01_2482] NVARCHAR(255) NULL,  -- 2482: Teléfono Contacto 01
    [toa_conexion_deco_01_2483] NVARCHAR(255) NULL,  -- 2483: Conexion Deco 01
    [toa_conexion_deco_02_2484] NVARCHAR(255) NULL,  -- 2484: Conexion Deco 02
    [toa_conexion_deco_03_2485] NVARCHAR(255) NULL,  -- 2485: Conexion Deco 03
    [toa_conexion_deco_04_2486] NVARCHAR(255) NULL,  -- 2486: Conexion Deco 04
    [toa_foto_de_equipo_modem_2488] NVARCHAR(255) NULL,  -- 2488: Foto de equipo modem
    [toa_motivo_quiebre_249] NVARCHAR(255) NULL,  -- 249: Motivo Quiebre
    [toa_causa_completado_reparacion_y_preventivo_adsl_250] NVARCHAR(255) NULL,  -- 250: Causa completado reparación y preventivo ADSL
    [toa_escenarios_2507] NVARCHAR(255) NULL,  -- 2507: Escenarios
    [toa_direccion_real_2508] NVARCHAR(255) NULL,  -- 2508: Dirección real
    [toa_direccion_errada_incompleta_2509] NVARCHAR(255) NULL,  -- 2509: Direccion errada\/incompleta
    [toa_codigo_completado_reparacion_y_preventivo_adsl_251] NVARCHAR(255) NULL,  -- 251: Código completado reparación y preventivo ADSL
    [toa_codigo_completado_reparacion_y_preventivo_cable_252] NVARCHAR(255) NULL,  -- 252: Código completado reparación y preventivo Cable
    [toa_codigo_completado_reparacion_y_preventivo_stb_254] NVARCHAR(255) NULL,  -- 254: Código completado reparación y preventivo STB
    [toa_causa_completado_reparacion_y_preventivo_stb_256] NVARCHAR(255) NULL,  -- 256: Causa completado reparación y preventivo STB
    [toa_causa_completado_reparacion_y_preventivo_cable_257] NVARCHAR(255) NULL,  -- 257: Causa completado reparación y preventivo Cable
    [toa_existe_cobertura_de_fibra_en_la_zona_2584] NVARCHAR(5) NULL,  -- 2584: ¿Existe cobertura de Fibra en la zona?
    [toa_tipo_de_vivienda_2585] NVARCHAR(100) NULL,  -- 2585: Tipo de Vivienda
    [toa_actualizacion_de_direccion_2586] NVARCHAR(5) NULL,  -- 2586: Actualización de Dirección
    [toa_numeracion_2588] NVARCHAR(100) NULL,  -- 2588: Numeración
    [toa_indicador_form_evalua_migra_2609] NVARCHAR(5) NULL,  -- 2609: Indicador Form. Evalua Migra
    [toa_cliente_desea_migrar_2610] NVARCHAR(255) NULL,  -- 2610: Cliente desea Migrar
    [toa_datos_de_contacto_1_2611] NVARCHAR(255) NULL,  -- 2611: Datos de Contacto 1
    [toa_datos_de_contacto_2_2612] NVARCHAR(255) NULL,  -- 2612: Datos de Contacto 2
    [toa_recomendacion_de_agenda_2613] NVARCHAR(255) NULL,  -- 2613: Recomendación de Agenda
    [toa_motivo_porque_no_dese_migrar_2614] NVARCHAR(255) NULL,  -- 2614: Motivo porque no dese migrar
    [toa_cliente_referidos_para_migracion_2615] NVARCHAR(255) NULL,  -- 2615: Cliente referidos para migración
    [toa_observacion_cliente_desea_migrar_2616] NVARCHAR(255) NULL,  -- 2616: Observacion cliente desea Migrar
    [toa_foto_de_1er_splitter_filtro_retorno_carga_f_2749] NVARCHAR(255) NULL,  -- 2749: Foto de 1er Splitter + Filtro retorno + Carga F
    [toa_foto_evidencia_2750] NVARCHAR(255) NULL,  -- 2750: Foto evidencia
    [toa_foto_de_domicilio_del_cliente_2796] NVARCHAR(255) NULL,  -- 2796: Foto de domicilio del cliente
    [toa_foto_de_fachada_domicilio_cliente_2852] NVARCHAR(255) NULL,  -- 2852: Foto de fachada domicilio cliente
    [toa_area_no_realizado_289] NVARCHAR(255) NULL,  -- 289: Área no realizado
    [toa_captura_de_coordenadas_297] NVARCHAR(100) NULL,  -- 297: Captura de Coordenadas
    [toa_codigo_de_peticion_309] NVARCHAR(255) NULL,  -- 309: Código de Petición
    [toa_orden_trabajo_368] NVARCHAR(255) NULL,  -- 368: Orden trabajo
    [toa_observaciones_en_toa_372] NVARCHAR(255) NULL,  -- 372: Observaciones en TOA
    [toa_ingresar_su_celular_387] NVARCHAR(255) NULL,  -- 387: Ingresar su Celular
    [toa_medicion_cto_3957] NVARCHAR(255) NULL,  -- 3957: Medicion CTO
    [toa_observacion_cobre_515] NVARCHAR(255) NULL,  -- 515: Observación Cobre
    [toa_telefono_de_contacto_570] NVARCHAR(50) NULL,  -- 570: Teléfono de Contacto
    [toa_foto_casa_del_cliente_601] NVARCHAR(255) NULL,  -- 601: Foto Casa del Cliente
    [toa_franja_postergacion_747] NVARCHAR(100) NULL,  -- 747: Franja Postergación
    [toa_foto_numero_de_casa_del_cliente_758] NVARCHAR(255) NULL,  -- 758: Foto Numero de Casa del Cliente
    [toa_flujo_tecnico_no_confiable_837] NVARCHAR(50) NULL,  -- 837: Flujo Técnico No Confiable
    [toa_actualizacion_de_direccion_849] NVARCHAR(5) NULL,  -- 849: Actualización de Dirección
    [toa_tipo_de_devolucion_reparacion_850] NVARCHAR(255) NULL,  -- 850: Tipo de Devolución Reparación
    [toa_sub_motivo_de_suspension_851] NVARCHAR(255) NULL,  -- 851: Sub Motivo de Suspensión
    [toa_inhabilitar_inventario_943] NVARCHAR(5) NULL,  -- 943: Inhabilitar Inventario
    [toa_foto_obligatoria_01_954] NVARCHAR(255) NULL,  -- 954: Foto Obligatoria 01
    [toa_foto_adicional_01_955] NVARCHAR(255) NULL,  -- 955: Foto Adicional 01
    [toa_a_company_bk] NVARCHAR(255) NULL,  -- A_COMPANY_BK: Empresa del Bucket
    [toa_a_ind_brigada] NVARCHAR(255) NULL,  -- A_IND_BRIGADA: Indicador de Brigada
    [toa_a_post_date] NVARCHAR(255) NULL,  -- A_POST_DATE: Postponement Date:
    [toa_a_registration_date] NVARCHAR(255) NULL,  -- A_REGISTRATION_DATE: Fecha Registro de Actividad en TOA
    [toa_xa_cancel_reason] NVARCHAR(255) NULL,  -- XA_CANCEL_REASON: Código Cierre Cancelada
    [toa_xa_channel_origin] NVARCHAR(255) NULL,  -- XA_CHANNEL_ORIGIN: Canal de Origen
    [toa_xa_customer_documentid] NVARCHAR(255) NULL,  -- XA_CUSTOMER_DOCUMENTID: Documento de Identidad
    [toa_xa_customer_type] NVARCHAR(255) NULL,  -- XA_CUSTOMER_TYPE: • Tipo de cliente
    [toa_xa_district_name] NVARCHAR(255) NULL,  -- XA_DISTRICT_NAME: • Nombre Distrito
    [toa_xa_documenttype] NVARCHAR(255) NULL,  -- XA_DOCUMENTTYPE: Tipo de documento
    [toa_xa_fecha_agenda] NVARCHAR(255) NULL,  -- XA_FECHA_AGENDA: Fecha de agendamiento
    [toa_xa_line_id] NVARCHAR(255) NULL,  -- XA_LINE_ID: LineId
    [toa_xa_pangea] NVARCHAR(255) NULL,  -- XA_PANGEA: Orden Pangea
    [toa_xa_priority] NVARCHAR(255) NULL,  -- XA_PRIORITY: • Prioridad
    [toa_xa_product_offers] NVARCHAR(255) NULL,  -- XA_PRODUCT_OFFERS: Ofertas de Productos/Servicios
    [toa_xa_system_agenda] NVARCHAR(255) NULL,  -- XA_SYSTEM_AGENDA: Canal de agendamiento
    [toa_xa_timeslot_agenda] NVARCHAR(255) NULL,  -- XA_TIMESLOT_AGENDA: Franja de agendamiento
    [toa_xa_user_agenda] NVARCHAR(255) NULL,  -- XA_USER_AGENDA: Usuario de agendamiento
    [toa_a_tsid] NVARCHAR(50) NULL,  -- a_tsid: • Franja
    [toa_aid] NVARCHAR(50) NULL,  -- aid: Número OT
    [toa_appt_number] NVARCHAR(100) NULL,  -- appt_number: • Work Order
    [toa_atime_of_booking] NVARCHAR(50) NULL,  -- atime_of_booking: • Fecha Registro de Legados
    [toa_aworktype] NVARCHAR(50) NULL,  -- aworktype: • Tipo de Actividad
    [toa_caddress] NVARCHAR(255) NULL,  -- caddress: • Dato Dirección
    [toa_ccity] NVARCHAR(100) NULL,  -- ccity: • Nombre Ciudad
    [toa_cname] NVARCHAR(100) NULL,  -- cname: • Nombre Cliente
    [toa_cstate] NVARCHAR(100) NULL,  -- cstate: • Nombre Departamento
    [toa_customer_number] NVARCHAR(50) NULL,  -- customer_number: • Código de Cliente
    [toa_date] NVARCHAR(255) NULL,  -- date: • Fecha de Cita:
    [toa_end_time] NVARCHAR(100) NULL,  -- end_time: Hora fin
    [toa_captura_de_coordenadas] NVARCHAR(255) NULL,  -- step_1: Captura de Coordenadas
    [toa_validar_coordenadas] NVARCHAR(255) NULL,  -- step_2: Validar Coordenadas
    [toa_pre_completado_averias] NVARCHAR(255) NULL,  -- step_3: Pre Completado Averías
    [toa_pre_suspension_actividad] NVARCHAR(255) NULL,  -- step_4: Pre Suspensión Actividad
    [toa_pre_devolucion_de_reparacion] NVARCHAR(255) NULL,  -- step_5: Pre Devolución de  Reparación
    [toa_tecnico_recuerde_que_debe_contactar_al_bo_de_su_contrata] NVARCHAR(255) NULL,  -- text#element_19: "Técnico,  recuerde que debe contactar al bo de su Contrata"
    [toa_por_favor_dejanos_tu_nro_celular_para_llamarte_antes_de_cerrar_tu_ticket_en_soditec] NVARCHAR(255) NULL,  -- text#element_23: Por favor déjanos tu nro. celular para llamarte antes de cerrar tu ticket en Soditec
    [toa_desea_validar_sus_coordenadas] NVARCHAR(255) NULL,  -- text#element_3: ¿Desea Validar sus Coordenadas ?
    [toa_iptv] NVARCHAR(255) NULL,  -- text#element_41: IPTV
    [toa_ingresar_direccion_completa_y_referencia] NVARCHAR(255) NULL,  -- text#element_7: Ingresar Dirección completa y referencia
    [toa_en_la_foto_de_evidencia_poner_la_foto_de_parametros_tv] NVARCHAR(255) NULL,  -- text#m9tenhgy_d62f1452: En la foto de Evidencia poner la Foto de Parametros TV
    [toa_en_la_foto_de_evidencia_opcional_poner_la_foto_de_fachada_del_cliente] NVARCHAR(255) NULL  -- text#m9tepzc6_881581db: En la foto de Evidencia Opcional poner la foto de fachada del cliente
;